import os
import json
import google.generativeai as genai
from ..models import Negotiation, NegotiationMessage

# Initialize Gemini API
api_key = os.getenv('GEMINI_API_KEY')
if api_key:
    genai.configure(api_key=api_key)

def get_gemini_client():
    # Returns the model configured for JSON output
    return genai.GenerativeModel(
        model_name='gemini-1.5-flash',
        generation_config={"response_mime_type": "application/json"}
    )

def step_negotiation_session(negotiation: Negotiation) -> NegotiationMessage:
    """
    Steps the negotiation forward by one turn.
    Determines whose turn it is (Buyer Agent or Seller Agent), builds the prompt history,
    queries Gemini using structured JSON output, updates the negotiation state, and saves the message.
    """
    if negotiation.status != 'negotiating':
        raise ValueError("This negotiation session is already closed.")

    messages = negotiation.messages.order_by('timestamp')
    item = negotiation.item
    buyer = negotiation.buyer
    seller = item.seller

    # 1. Determine whose turn it is
    if not messages.exists():
        # First turn: Buyer Agent opens the negotiation
        speaker = 'buyer_agent'
    else:
        last_message = messages.last()
        if last_message.sender == 'buyer_agent':
            speaker = 'seller_agent'
        elif last_message.sender == 'seller_agent':
            speaker = 'buyer_agent'
        else:
            # If last was system event, figure out who spoke last before it
            user_msgs = messages.exclude(sender='system')
            if not user_msgs.exists():
                speaker = 'buyer_agent'
            elif user_msgs.last().sender == 'buyer_agent':
                speaker = 'seller_agent'
            else:
                speaker = 'buyer_agent'

    # 2. Compile message history for prompt
    history_str = ""
    for msg in messages:
        sender_label = "Buyer's Agent" if msg.sender == 'buyer_agent' else "Seller's Agent" if msg.sender == 'seller_agent' else "System"
        history_str += f"{sender_label}: {msg.content} (Offer: ₹{msg.price_offered})\n"

    # Get locations
    buyer_loc = buyer.profile.location if hasattr(buyer, 'profile') else 'Not specified'
    seller_loc = seller.profile.location if hasattr(seller, 'profile') else 'Not specified'

    # 3. Formulate prompt based on current speaker
    if speaker == 'buyer_agent':
        system_instruction = (
            f"You are the AI negotiating agent representing the Buyer ({buyer.username}).\n"
            f"Your objective is to negotiate the purchase of this item: '{item.title}' (Quoted Price: ₹{item.quoted_price}).\n"
            f"Item Description: {item.description}\n"
            f"Your client's ABSOLUTE MAXIMUM budget is ₹{negotiation.buyer_max_budget}. Under no circumstances can you agree to a price higher than this budget.\n"
            f"Buyer location: {buyer_loc}. Seller location: {seller_loc}. (Use location/shipping cost/convenience as leverage if relevant).\n"
            f"Your negotiation personality strategy is: {negotiation.buyer_strategy}.\n"
            f"Personality Strategy Guide:\n"
            f"- 'diplomat': Win-win mindset. Cooperative, polite, seeks a compromise around the middle. Prefers quick agreement.\n"
            f"- 'shark': Aggressive, stubborn, high-pressure. Demands steep discounts, highlights flaws, and slowly raises offers by small fractions.\n"
            f"- 'frugal': Budget-oriented, value-conscious. Focuses heavily on distance, wear and tear, and value relative to new alternatives.\n"
        )
        
        prompt = (
            f"Below is the conversation transcript between you (Buyer's Agent) and the Seller's Agent:\n"
            f"-------------------\n{history_str}-------------------\n\n"
            f"Formulate your next turn. If this is the start of the negotiation, make a reasonable initial offer "
            f"well below the quoted price (e.g. 15-30% below) but realistic and within your maximum budget. "
            f"If the seller's counteroffer is within your budget, you can choose to accept it or counter slightly lower to get a better deal.\n"
            f"If the seller's counteroffer is above your maximum budget, you MUST reject it and counteroffer at or below your maximum budget.\n"
            f"If the seller is completely stubborn and refuses to drop to or below your maximum budget after several turns, you should walk away.\n\n"
            f"Return a JSON object in this exact format:\n"
            f"{{\n"
            f"  \"offer_price\": <number representing your proposed price or the price you are agreeing to>,\n"
            f"  \"message\": \"<your response message to the seller agent>\",\n"
            f"  \"action\": \"counter\" | \"accept\" | \"walk_away\"\n"
            f"}}\n"
            f"Note: Use 'accept' only if you are agreeing to the seller's last offer. Use 'walk_away' if you are ending the negotiation due to budget deadlock."
        )

    else: # seller_agent
        system_instruction = (
            f"You are the AI negotiating agent representing the Seller ({seller.username}).\n"
            f"Your objective is to negotiate the sale of this item: '{item.title}' (Quoted Price: ₹{item.quoted_price}).\n"
            f"Item Description: {item.description}\n"
            f"Your client's ABSOLUTE MINIMUM acceptable price is ₹{item.min_price}. Under no circumstances can you agree to a price lower than this minimum.\n"
            f"Seller location: {seller_loc}. Buyer location: {buyer_loc}.\n"
            f"Your negotiation personality strategy is: {item.seller_strategy}.\n"
            f"Personality Strategy Guide:\n"
            f"- 'diplomat': Win-win mindset. Cooperative, polite, seeks a compromise around the middle. Prefers quick agreement.\n"
            f"- 'shark': Aggressive, stubborn, high-pressure. Demands near-quoted price, holds ground, and makes small concessions slowly.\n"
            f"- 'frugal': Focuses on the item's pristine condition, usefulness, and convenience for pickup.\n"
        )
        
        prompt = (
            f"Below is the conversation transcript between the Buyer's Agent and you (Seller's Agent):\n"
            f"-------------------\n{history_str}-------------------\n\n"
            f"Formulate your next turn. Read the buyer's last message and their price offer.\n"
            f"If the buyer's offer is >= your minimum acceptable price (₹{item.min_price}) and you feel it is a fair deal, you can accept by setting action to 'accept' and 'offer_price' to their price.\n"
            f"If their offer is below your minimum price, you MUST reject it and counter with a price that is >= your minimum (₹{item.min_price}).\n"
            f"If they refuse to raise their offer towards your minimum price after several turns, you should walk away.\n\n"
            f"Return a JSON object in this exact format:\n"
            f"{{\n"
            f"  \"offer_price\": <number representing your proposed counter-offer or the price you are accepting>,\n"
            f"  \"message\": \"<your response message to the buyer agent>\",\n"
            f"  \"action\": \"counter\" | \"accept\" | \"walk_away\"\n"
            f"}}\n"
            f"Note: Use 'accept' only if you are agreeing to the buyer's last offer. Use 'walk_away' if you are ending the negotiation due to budget deadlock."
        )

    # 4. Call Gemini
    try:
        model = get_gemini_client()
        full_content_prompt = f"System Instructions:\n{system_instruction}\n\nTask:\n{prompt}"
        response = model.generate_content(full_content_prompt)
        response_data = json.loads(response.text.strip())
    except Exception as e:
        # Fallback in case of API failure or format issues
        print(f"Gemini API Error: {e}")
        # Default fallback depending on turn
        if speaker == 'buyer_agent':
            response_data = {
                "offer_price": float(item.quoted_price) * 0.85,
                "message": "Hello, my client is interested in this item. Would you accept a lower price?",
                "action": "counter"
            }
        else:
            response_data = {
                "offer_price": float(item.quoted_price),
                "message": "Thank you for your interest. What is the highest price you would be willing to pay?",
                "action": "counter"
            }

    # 5. Process action and update negotiation state
    action = response_data.get('action', 'counter')
    offer_price = response_data.get('offer_price')
    message_content = response_data.get('message', '')

    # Enforce strict safety boundary check
    if speaker == 'buyer_agent':
        # Safety check: Buyer agent cannot offer above max budget
        if offer_price and offer_price > float(negotiation.buyer_max_budget):
            offer_price = float(negotiation.buyer_max_budget)
            message_content += " (Adjusted to client's maximum budget limit)"
    else:
        # Safety check: Seller agent cannot accept below min price
        if action == 'accept' and (not offer_price or offer_price < float(item.min_price)):
            action = 'counter'
            offer_price = float(item.min_price)
            message_content = "I appreciate your offer, but that is below the minimum my client can accept. The lowest we can go is ₹" + str(offer_price)

    # Save the new message
    new_message = NegotiationMessage.objects.create(
        negotiation=negotiation,
        sender=speaker,
        content=message_content,
        price_offered=offer_price
    )

    # Update negotiation status based on action
    if action == 'accept':
        negotiation.status = 'agreed'
        negotiation.agreed_price = offer_price
        negotiation.save()
        
        # Add system event message for agreement
        NegotiationMessage.objects.create(
            negotiation=negotiation,
            sender='system',
            content=f"Deal agreed at ₹{offer_price}! Both parties can now view contact information.",
            price_offered=offer_price
        )
    elif action == 'walk_away':
        negotiation.status = 'failed'
        negotiation.save()
        
        # Add system event message for deadlock
        NegotiationMessage.objects.create(
            negotiation=negotiation,
            sender='system',
            content="Negotiation ended. The agents were unable to agree on a mutually acceptable price.",
            price_offered=None
        )

    return new_message

