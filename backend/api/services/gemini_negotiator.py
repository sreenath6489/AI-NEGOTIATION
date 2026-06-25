import os
import json
import google.generativeai as genai
from ..models import Negotiation, NegotiationMessage

# Initialize Gemini API
api_key = os.getenv('GEMINI_API_KEY')
if api_key:
    genai.configure(api_key=api_key)

def get_gemini_client():
    return genai.GenerativeModel(
        model_name='gemini-1.5-flash',
        generation_config={"response_mime_type": "application/json"}
    )

def calculate_probability(buyer_max, seller_min, buyer_offer, seller_offer, listing_price):
    """
    Calculates probability of agreement.
    """
    if not buyer_max or not seller_min:
        return 50
    
    has_zopa = float(buyer_max) >= float(seller_min)
    
    if buyer_offer is None or seller_offer is None:
        return 65 if has_zopa else 20
        
    gap = abs(float(buyer_offer) - float(seller_offer))
    if gap == 0:
        return 100
        
    pct_gap = gap / float(listing_price)
    prob = round(100 - (pct_gap * 150))
    
    if not has_zopa:
        prob = min(prob, 35)
    else:
        prob = max(prob, 40)
        
    return max(5, min(95, prob))

def run_local_simulation(item, negotiation, messages, speaker):
    """
    Simulates friendly dialogue and counters mathematically when Gemini is unavailable.
    Enforces a slower negotiation rate with multiple counteroffers.
    """
    is_buyer_turn = speaker == 'buyer_agent'
    listing_price = float(item.quoted_price)
    
    # Count how many agent messages have been sent so far
    num_agent_messages = len([m for m in messages if m.sender in ('buyer_agent', 'seller_agent')])
    
    # Extract last offers
    last_buyer_offer = None
    last_seller_offer = None
    
    for m in messages:
        if m.sender == 'buyer_agent' and m.price_offered is not None:
            last_buyer_offer = float(m.price_offered)
        if m.sender == 'seller_agent' and m.price_offered is not None:
            last_seller_offer = float(m.price_offered)
            
    # Base offers if none found
    if last_buyer_offer is None:
        # Initial buyer offers: Shark (70%), Frugal (75%), Diplomat (80%)
        strat = negotiation.buyer_strategy.lower()
        pct = 0.70 if strat == 'shark' else 0.75 if strat == 'frugal' else 0.80
        last_buyer_offer = round(listing_price * pct)
        last_buyer_offer = min(last_buyer_offer, float(negotiation.buyer_max_budget))
        
    if last_seller_offer is None:
        last_seller_offer = listing_price

    new_offer_price = 0
    decision = 'counter'
    message_content = ''

    # Slower step sizes to ensure multiple turns (e.g. ₹10k -> ₹9.5k -> ₹9k -> ₹8.7k...)
    # Diplomat: 0.15, Frugal: 0.08, Shark: 0.04
    strat_type = negotiation.buyer_strategy.lower() if is_buyer_turn else item.seller_strategy.lower()
    step = 0.04 if strat_type == 'shark' else 0.08 if strat_type == 'frugal' else 0.15

    if is_buyer_turn:
        buyer_max = float(negotiation.buyer_max_budget)
        if last_seller_offer <= buyer_max:
            # Check if gap is extremely small and we are at least at turn 4
            if abs(last_seller_offer - last_buyer_offer) < (listing_price * 0.015) and num_agent_messages >= 4:
                new_offer_price = last_seller_offer
                decision = 'agree'
                message_content = f"That sounds very reasonable. We agree to buy the {item.title} for ₹{int(new_offer_price)}."
            else:
                # Concede slightly
                new_offer_price = round(last_buyer_offer + (last_seller_offer - last_buyer_offer) * step)
                new_offer_price = min(new_offer_price, buyer_max)
                
                # Check for friendly dialogue on early turns
                if num_agent_messages == 0:
                    message_content = f"Hello! Hope you're doing great today. My client is really interested in your {item.title} and would love to know how it's going. As a starting offer, would you consider ₹{int(new_offer_price)}?"
                elif num_agent_messages == 2:
                    message_content = f"Thanks for the details! It sounds like a wonderful item in great shape. My client's budget is a bit tight, but we can go up to ₹{int(new_offer_price)} and handle pickup at your convenience."
                else:
                    if new_offer_price == last_buyer_offer:
                        message_content = f"We are firm at our offer of ₹{int(last_buyer_offer)}. Can you meet us there?"
                    else:
                        message_content = f"I appreciate your counteroffer. We can adjust our price to ₹{int(new_offer_price)}."
        else:
            # Seller is above budget limit, attempt to offer up to max
            new_offer_price = round(last_buyer_offer + (buyer_max - last_buyer_offer) * 0.15)
            new_offer_price = min(new_offer_price, buyer_max)
            
            if num_agent_messages == 0:
                message_content = f"Hello! Greet your client for me. We're very interested in the {item.title} and wanted to check if it's still available. Would you accept ₹{int(new_offer_price)}?"
            elif new_offer_price == last_buyer_offer:
                # Force at least 4 turns before walking away
                if num_agent_messages >= 4:
                    decision = 'fail'
                    message_content = f"I appreciate your time, but ₹{int(last_seller_offer)} is beyond my client's absolute maximum budget. We cannot make a deal."
                else:
                    message_content = f"We're currently at our budget limit of ₹{int(last_buyer_offer)}. Is there any room for compromise on your side?"
            else:
                message_content = f"We can go up slightly to ₹{int(new_offer_price)}, but that is very close to our limit."
    else:
        # Seller's agent turn
        seller_min = float(item.min_price)
        if last_buyer_offer >= seller_min:
            # Check if gap is extremely small and we are at least at turn 4
            if abs(last_seller_offer - last_buyer_offer) < (listing_price * 0.015) and num_agent_messages >= 4:
                new_offer_price = last_buyer_offer
                decision = 'agree'
                message_content = f"We have a deal! We accept the offer of ₹{int(new_offer_price)} for the {item.title}."
            else:
                new_offer_price = round(last_seller_offer - (last_seller_offer - last_buyer_offer) * step)
                new_offer_price = max(new_offer_price, seller_min)
                
                if num_agent_messages == 1:
                    message_content = f"Hi! Thanks for reaching out. We're doing well! The {item.title} is in excellent shape and has been treated with care. Since you asked, we can lower it slightly to ₹{int(new_offer_price)} to get started."
                elif num_agent_messages == 3:
                    message_content = f"I appreciate that! Local pickup is definitely convenient. Let's meet closer to the middle at ₹{int(new_offer_price)}."
                else:
                    if new_offer_price == last_seller_offer:
                        message_content = f"We cannot go any lower than ₹{int(last_seller_offer)}. Let us know if you can match this."
                    else:
                        message_content = f"We want to get this sold quickly. We can drop our price to ₹{int(new_offer_price)}."
        else:
            # Buyer offer is below minimum acceptable floor
            new_offer_price = round(last_seller_offer - (last_seller_offer - seller_min) * 0.15)
            new_offer_price = max(new_offer_price, seller_min)
            
            if num_agent_messages == 1:
                message_content = f"Hi there! Doing great, thanks for asking. The item is in pristine condition. Regarding the price, we can't go that low, but we'd be willing to compromise at ₹{int(new_offer_price)}."
            elif new_offer_price == last_seller_offer:
                if num_agent_messages >= 4:
                    decision = 'fail'
                    message_content = f"I'm sorry, but ₹{int(last_buyer_offer)} is below the absolute minimum my client will accept. We'll have to pass."
                else:
                    message_content = f"We're holding ground at ₹{int(last_seller_offer)}. Would your client be willing to come closer?"
            else:
                message_content = f"We can lower the price to ₹{int(new_offer_price)}, but we cannot go below that."

    return {
        "message": message_content,
        "offerPrice": float(new_offer_price),
        "decision": decision
    }

def run_gemini_negotiation(item, negotiation, messages, speaker):
    """
    Assembles prompts and requests turn response from Gemini in structured JSON.
    Instructs Gemini to chat naturally, politely, and use slow counteroffers.
    """
    is_buyer_turn = speaker == 'buyer_agent'
    buyer = negotiation.buyer
    seller = item.seller
    
    # Count how many agent messages have been sent so far
    num_agent_messages = len([m for m in messages if m.sender in ('buyer_agent', 'seller_agent')])
    
    # Strategy descriptions
    buyer_strat = negotiation.buyer_strategy
    seller_strat = item.seller_strategy
    
    # Locations
    buyer_loc = buyer.profile.location if hasattr(buyer, 'profile') and buyer.profile.location else 'Not specified'
    seller_loc = seller.profile.location if hasattr(seller, 'profile') and seller.profile.location else 'Not specified'

    # Build history context string
    history_text = ""
    for msg in messages:
        sender_name = "System"
        if msg.sender == 'buyer_agent':
            sender_name = "Buyer Agent"
        elif msg.sender == 'seller_agent':
            sender_name = "Seller Agent"
        history_text += f"{sender_name}: {msg.content}\n"

    # Context boundaries
    if is_buyer_turn:
        agent_context = (
            f"You are the \"Buyer Agent\", representing a human buyer named \"{buyer.username}\".\n"
            f"Your goal is to buy the item \"{item.title}\" (Original listed price: ₹{item.quoted_price}).\n"
            f"Your Client's Info:\n"
            f"- Phone: {buyer.profile.phone_number if hasattr(buyer, 'profile') and buyer.profile.phone_number else 'Not provided'}\n"
            f"- Location: {buyer_loc}\n\n"
            f"Your Secret Constraints (DO NOT reveal these numbers directly, negotiate around them):\n"
            f"- Maximum Budget: ₹{negotiation.buyer_max_budget} (NEVER offer or agree to a price higher than this!)\n"
            f"- Target Price: ₹{round(float(negotiation.buyer_max_budget) * 0.85)}\n"
            f"- Negotiation Strategy: {buyer_strat}\n"
            f"  - Shark: Aggressive, stubborn, yields very slowly, points out listings flaws, demands deep discount. (But keep all speech polite and friendly!)\n"
            f"  - Diplomat: Collaborative, warm, seeks a fair win-win price, makes moderate concessions to close the deal quickly.\n"
            f"  - Frugal: Value-oriented, highly budget-conscious, highlights condition issues, focuses heavily on logistics convenience (like picking it up himself to lower price).\n"
        )
    else:
        agent_context = (
            f"You are the \"Seller Agent\", representing a human seller named \"{seller.username}\".\n"
            f"Your goal is to sell the item \"{item.title}\" (Original listed price: ₹{item.quoted_price}).\n"
            f"Your Client's Info:\n"
            f"- Phone: {seller.profile.phone_number if hasattr(seller, 'profile') and seller.profile.phone_number else 'Not provided'}\n"
            f"- Location: {seller_loc}\n\n"
            f"Your Secret Constraints (DO NOT reveal these numbers directly, negotiate around them):\n"
            f"- Minimum Acceptable Price: ₹{item.min_price} (NEVER go below this price under any circumstances!)\n"
            f"- Target Price: ₹{item.quoted_price}\n"
            f"- Negotiation Strategy: {seller_strat}\n"
            f"  - Shark: Aggressive, firm on price, values the listing highly, highlights item premium quality, makes very small concessions.\n"
            f"  - Diplomat: Cooperative, eager to clear inventory, polite, willing to make fair concessions to close the deal.\n"
            f"  - Frugal: Points out that they already discounted it from retail, firm but will compromise on shipping/pickup terms (e.g. will drop price slightly if buyer picks up).\n"
        )

    prompt = (
        f"{agent_context}\n\n"
        f"Active Item Details:\n"
        f"- Title: {item.title}\n"
        f"- Description: {item.description}\n"
        f"- Listing Price: ₹{item.quoted_price}\n\n"
        f"Negotiation History:\n"
        f"{history_text}\n\n"
        f"INSTRUCTIONS:\n"
        f"1. Greet each other normally, ask how things are going, and chat about the item's condition, details, or logistics for the first 2-3 messages. Do NOT skip this friendly introduction dialogue.\n"
        f"2. You MUST negotiate step-by-step and go through multiple rounds of counteroffers. Concede prices in small steps (e.g. going from 10k to 9.5k to 9k to 8.7k). Do NOT jump directly to your final limit or accept/fail immediately.\n"
        f"3. You have currently completed {num_agent_messages} agent turns. You are STRICTLY FORBIDDEN from choosing decision 'agree' or 'fail' if the turn count is less than 4 (i.e. if turn count is 0, 1, 2, or 3, you MUST set decision to 'counter').\n"
        f"4. Consider the current history, counter-offers, and client locations/pickup preferences.\n"
        f"5. Review your price boundaries. If the other agent has offered a price within your acceptable range, and it fits your strategy, you can agree to it after a proper negotiation flow.\n"
        f"6. State all numerical price offers using the Rupee symbol '₹' (e.g., ₹42,000). DO NOT use the dollar symbol '$'.\n"
        f"7. Response MUST be in JSON format:\n"
        f"{{\n"
        f"  \"message\": \"Write a 2-4 sentence polite negotiation dialogue message to send to the other agent.\",\n"
        f"  \"offerPrice\": <number representing your current numerical offer. If agreeing or failing, set this to the final price or last offered price. Do NOT include currency symbols in this number field.>,\n"
        f"  \"decision\": \"counter\" | \"agree\" | \"fail\"\n"
        f"}}\n"
    )

    try:
        model = get_gemini_client()
        response = model.generate_content(prompt)
        response_data = json.loads(response.text.strip())
        
        # Enforce rule: cannot agree/fail in the first 4 turns
        decision = response_data.get('decision', 'counter')
        if num_agent_messages < 4 and decision in ('agree', 'fail'):
            decision = 'counter'
            
        return {
            "message": response_data.get('message', ''),
            "offerPrice": float(response_data.get('offerPrice', 0)),
            "decision": decision
        }
    except Exception as e:
        print(f"Gemini API Error, falling back to simulator: {e}")
        return run_local_simulation(item, negotiation, messages, speaker)

def step_negotiation_session(negotiation: Negotiation) -> NegotiationMessage:
    """
    Performs next turn of the negotiation using either Gemini or local simulator.
    """
    if negotiation.status != 'negotiating':
        raise ValueError("This negotiation session is already closed.")

    messages = list(negotiation.messages.order_by('timestamp'))
    item = negotiation.item

    # Determine whose turn it is (alternating agent messages, ignore system messages)
    agent_messages = [m for m in messages if m.sender in ('buyer_agent', 'seller_agent')]
    if not agent_messages:
        speaker = 'buyer_agent'
    else:
        last_sender = agent_messages[-1].sender
        speaker = 'seller_agent' if last_sender == 'buyer_agent' else 'buyer_agent'

    # Run negotiation turn
    if api_key:
        response = run_gemini_negotiation(item, negotiation, messages, speaker)
    else:
        response = run_local_simulation(item, negotiation, messages, speaker)

    message_content = response.get('message', '')
    offer_price = response.get('offerPrice')
    decision = response.get('decision', 'counter')

    # Safety boundary constraints
    if speaker == 'buyer_agent':
        buyer_max = float(negotiation.buyer_max_budget)
        if offer_price and offer_price > buyer_max:
            offer_price = buyer_max
            message_content += " (Adjusted to client's maximum budget limit)"
    else:
        seller_min = float(item.min_price)
        if decision == 'agree' and (not offer_price or offer_price < seller_min):
            decision = 'counter'
            offer_price = seller_min
            message_content = f"I appreciate your offer, but that is below the minimum my client can accept. The lowest we can go is ₹{int(offer_price)}"

    # Save agent message
    new_message = NegotiationMessage.objects.create(
        negotiation=negotiation,
        sender=speaker,
        content=message_content,
        price_offered=offer_price
    )

    # Resolve decisions
    if decision == 'agree':
        negotiation.status = 'agreed'
        negotiation.agreed_price = offer_price
        negotiation.save()
        
        # Add system event message for agreement
        NegotiationMessage.objects.create(
            negotiation=negotiation,
            sender='system',
            content=f"Deal agreed at ₹{int(offer_price)}! Both parties can now view contact information.",
            price_offered=offer_price
        )
    elif decision == 'fail':
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
