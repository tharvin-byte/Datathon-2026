import csv
import random
from datetime import datetime, timedelta

# Set seed for reproducible, high-complexity deterministic benchmark dataset
random.seed(108)

DISTRICTS = [
    "Mysuru", "Bengaluru", "Mangaluru", "Hubballi", "Belagavi", 
    "Ballari", "Kalaburagi", "Shivamogga", "Tumakuru", "Udupi",
    "Dharwad", "Mandya", "Hassan", "Chikkamagaluru", "Vijayapura"
]

CRIME_TYPES = [
    "Burglary", "Extortion", "Robbery", "Arms Trafficking", "Cybercrime",
    "Money Laundering", "Narcotics", "Smuggling", "Assault", "Kidnapping",
    "Vehicle Theft", "Rioting", "Counterfeiting", "Fraud", "Murder", "Arson"
]

# 8 Complex Interconnected Syndicates with deep ties, cross-member links & MO clusters
SYNDICATES = [
    {
        "name": "Devaraja Urs Vault & Gold Cartel",
        "primary_districts": ["Mysuru", "Mandya", "Hassan"],
        "crime_focus": ["Burglary", "Robbery", "Arson", "Counterfeiting"],
        "kingpin": "Raju Gowda",
        "members": ["Anand Verma", "Raghavendra 'Raghu'", "Shiva 'Gas'", "Balu 'Cheetah'", "Santhosh 'Oxy'", "Gowrish", "Suresha"],
        "mo_templates": [
            "Armed crew raided a commercial jewelry vault on {location} at 02:30 AM using high-pressure oxy-acetylene torches. Stole {amount} kg of gold ingots and escaped in a black SUV.",
            "Apprehended near {location} while operating an illicit foundry converting {amount} kg of stolen gold bangles into untraceable bullion bars.",
            "Set fire to a retail warehouse on {location} after the proprietor refused extortion demands issued by Raju Gowda.",
            "Operated a counterfeit currency printing press in {location} distributing fake Rs 500 notes to finance local robbery getaway vehicles."
        ],
        "locations": ["Devaraja Urs Road", "Saraswathipuram", "Vijayanagar Industrial Area", "Mandya Highway Checkpoint"]
    },
    {
        "name": "Coastal Cyber Hawala Network",
        "primary_districts": ["Mangaluru", "Udupi", "Hubballi"],
        "crime_focus": ["Cybercrime", "Money Laundering", "Fraud", "Counterfeiting"],
        "kingpin": "Zaid Khan",
        "members": ["Imran Pasha", "Rohan D'Souza", "Sameer 'Sam'", "Devdas Kamath", "Sanath", "Srinivas 'Tech'"],
        "mo_templates": [
            "Installed deep-insert ATM skimming hardware and pinhole cameras across bank kiosks near {location}. Captured data of {count} debit cards.",
            "Laundered Rs {amount} Lakhs derived from online investment scams through a network of mule bank accounts registered in {location}.",
            "Operated an illegal SIM-box gateway in {location} routing international phishing calls to mask syndicate cyber extortion communications.",
            "Seized with {count} cloned NFC smart cards and crypto hardware wallets used to move hawala cash across coastal ports."
        ],
        "locations": ["Hampankatta Commercial Hub", "Bunder Port Road", "Manipal University Road", "Malpe Harbor"]
    },
    {
        "name": "Silicon Valley Synthetic Narcotics Syndicate",
        "primary_districts": ["Bengaluru", "Mysuru", "Tumakuru"],
        "crime_focus": ["Narcotics", "Cybercrime", "Money Laundering", "Arms Trafficking"],
        "kingpin": "Karan 'Bhai' Sharma",
        "members": ["Naveen Raj", "Pooja Hegde", "Siddharth Mehta", "Ayesha 'Queen'", "Chandan Kumar", "Sunny 'DJ'"],
        "mo_templates": [
            "Intercepted on {location} transporting {amount} kg of synthetic MDMA crystals hidden inside modified speaker enclosures of a cargo van.",
            "Coordinated phishing SMS campaigns targeting net banking users. Channeled proceeds into dark web crypto wallets managed by Karan Sharma.",
            "Chartered accountant arrested in {location} for incorporating shell entities to absorb illegal narcotics revenues.",
            "Distributed synthetic drug packages to nightlife venues across {location} using encrypted messaging channels."
        ],
        "locations": ["Electronic City Phase 2", "Koramangala 4th Block", "Indiranagar 100ft Road", "HSR Layout"]
    },
    {
        "name": "Ballari Iron Belt Extortion Gang",
        "primary_districts": ["Ballari", "Koppal", "Raichur"],
        "crime_focus": ["Extortion", "Assault", "Smuggling", "Murder"],
        "kingpin": "Reddy 'Dora'",
        "members": ["Veerabhadraappa", "Muni 'Rowdy'", "Kondaiah", "Sekhar", "Yellappa", "Giddaiah"],
        "mo_templates": [
            "Extorted protection fees from iron ore mining fleet operators along {location} under threat of armed violence.",
            "Assaulted commercial truck drivers along {location} using iron rods for resisting daily illegal highway tolls.",
            "Intercepted transporting {amount} tonnes of illegally mined ore with forged transport permits near {location}.",
            "Targeted shooting of a transport contractor near {location} to maintain monopoly over mining logistics lines."
        ],
        "locations": ["Hospet Mining Belt", "Toranagallu Highway", "Sandur Quarry Road", "Ballari APMC Yard"]
    },
    {
        "name": "Western Ghats Timber & Wildlife Ring",
        "primary_districts": ["Shivamogga", "Chikkamagaluru", "Hassan"],
        "crime_focus": ["Smuggling", "Narcotics", "Vehicle Theft", "Assault"],
        "kingpin": "Nagaraj 'Forest'",
        "members": ["Basavaraj Naik", "Harish 'Ganja'", "Manja 'Blade'", "Lokesh", "Gajendra", "Narasimha"],
        "mo_templates": [
            "Caught smuggling {amount} kg of contraband red sanders logs and wildlife skins through {location} forest checkpost.",
            "Attacked forest patrol officers near {location} with sharp weapons, facilitating getaway of a timber truck convoy.",
            "Cultivated illegal cannabis plantations spanning {count} acres inside dense forest reserves near {location}.",
            "Stole off-road tractors and winches from tea estates near {location} to haul felled timber through rough terrain."
        ],
        "locations": ["Bhadra Wildlife Corridor", "Agumbe Forest Reserve", "Sakleshpur Timber Depot", "Mudigere Border"]
    },
    {
        "name": "Northern Border Interstate Arms Syndicate",
        "primary_districts": ["Belagavi", "Kalaburagi", "Vijayapura"],
        "crime_focus": ["Arms Trafficking", "Robbery", "Dacoity", "Rioting"],
        "kingpin": "Tariq Anwar",
        "members": ["Suresh Kumar", "Subhash 'Fauji'", "Sachin Shinde", "Ganesh 'Gunner'", "Bhimrao"],
        "mo_templates": [
            "Intercepted at {location} border checkpost carrying {count} illegal semi-automatic pistols and ammunition.",
            "Highway robbery of a cash transit van on {location} using illicit firearms, looting Rs {amount} Lakhs.",
            "Procured country-made revolvers and carbines across the state border for distribution to urban crime crews.",
            "Enforced extortion demands on quarry operators near {location} using illegal firearms supplied by Subhash Fauji."
        ],
        "locations": ["Nipani Border Checkpost", "NH-4 Highway Belt", "Shahapur Quarry Area", "Vijayapura City Outskirts"]
    },
    {
        "name": "Hubballi Commercial Bank & APMC Heist Crew",
        "primary_districts": ["Hubballi", "Dharwad", "Belagavi"],
        "crime_focus": ["Burglary", "Extortion", "Rioting", "Fraud"],
        "kingpin": "Santosh Patil",
        "members": ["Manjunath 'Sunil' Desai", "Prakash Jhadav", "Vinay 'Vinu'", "Ashok 'Auto' Mani", "Laxman 'Laxi'"],
        "mo_templates": [
            "Midnight bank robbery at a cooperative branch in {location}. Bypassed security alarms and drilled vault door.",
            "Extorted Rs {amount} Lakhs from a commercial trader in {location} under threat of arson against shop premises.",
            "Instigated market riots in {location} to distract law enforcement during planned burglary operations.",
            "Fabricated master keys and safe-cracking tools used in commercial burglaries across {location}."
        ],
        "locations": ["Vidyanagar Bank Circle", "Hubballi APMC Market", "Gokul Road Industrial Area", "Dharwad Court Road"]
    },
    {
        "name": "Central Getaway & Chop-Shop Syndicate",
        "primary_districts": ["Mysuru", "Bengaluru", "Mandya"],
        "crime_focus": ["Vehicle Theft", "Robbery", "Burglary", "Assault"],
        "kingpin": "Syed Ali",
        "members": ["Muralidhar", "Imran 'Bike'", "Farhan 'Auto'", "Salman", "Prashanth 'Pachhi'"],
        "mo_templates": [
            "Stole luxury SUVs and motorcycles from residential parking lots across {location} for use as robbery getaway vehicles.",
            "Operated a clandestine chop-shop in {location} altering engine numbers of stolen trucks to evade police checkpoints.",
            "Robbed a diamond merchant near {location} and escaped on modified stolen motorcycles supplied by Syed Ali.",
            "Engaged in a violent street clash near {location} with rival vehicle thieves to control regional chop-shop operations."
        ],
        "locations": ["Gokulam Residential Area", "Peenya Industrial Area", "Jayalakshmipuram Ring Road", "Saraswathipuram"]
    }
]

# Generate exactly 500 rows (C5001 to C5500)
TOTAL_ROWS = 500
START_ID = 5001
START_DATE = datetime(2026, 1, 1)

rows = []
syndicate_case_history = {i: [] for i in range(len(SYNDICATES))}

for i in range(TOTAL_ROWS):
    case_id = f"C{START_ID + i}"
    # Date progresses realistically over 2026
    case_date = (START_DATE + timedelta(days=int(i * 0.72))).strftime("%Y-%m-%d")
    
    # Pick syndicate with high interaction density
    syn_idx = i % len(SYNDICATES)
    syn = SYNDICATES[syn_idx]
    syndicate_case_history[syn_idx].append(case_id)
    
    district = random.choice(syn["primary_districts"])
    crime_type = random.choice(syn["crime_focus"])
    
    # Pick accused (18% Kingpin, 82% Members)
    if random.random() < 0.18:
        accused_name = syn["kingpin"]
    else:
        accused_name = random.choice(syn["members"])
        
    # Build co_accused_ids referencing past cases in same or adjacent syndicate
    co_accused_cases = []
    past_cases = [c for c in syndicate_case_history[syn_idx] if c != case_id][-5:]
    if past_cases:
        num = random.randint(1, min(2, len(past_cases)))
        co_accused_cases.extend(random.sample(past_cases, num))
        
    # 25% chance of inter-syndicate cross-linking for network density
    if random.random() < 0.25 and i > 8:
        adj_idx = (syn_idx + random.choice([-1, 1])) % len(SYNDICATES)
        if syndicate_case_history[adj_idx]:
            co_accused_cases.append(random.choice(syndicate_case_history[adj_idx][-3:]))
            
    co_accused_ids = ";".join(sorted(list(set(co_accused_cases)))) if co_accused_cases else f"C{START_ID + max(0, i - random.randint(1, 4))}"
    
    # Formulate narrative description sentence containing structured facts + forensic cross-references
    template = random.choice(syn["mo_templates"])
    location = random.choice(syn["locations"])
    amount = random.randint(12, 180)
    count = random.randint(30, 500)
    
    base_narrative = template.format(location=location, amount=amount, count=count)
    
    forensic_details = [
        f"Call detail records confirmed {accused_name} was in continuous contact with syndicate kingpin {syn['kingpin']} during the operation.",
        f"Forensic examination of seized burner mobile phones revealed encrypted chat logs discussing stolen contraband movement.",
        f"CCTV camera feeds near {location} captured {accused_name} coordinating escape routes with co-accused operatives.",
        f"Ballistic matching linked recovered shell casings directly to prior armed robbery case files in {district} district.",
        f"Financial audit uncovered illicit hawala transfers used to settle cartel accounts across regional checkposts."
    ]
    
    full_description = f"{base_narrative} {random.choice(forensic_details)}"
    
    rows.append([case_id, case_date, district, crime_type, accused_name, co_accused_ids, full_description])

# Write to both locations
output_paths = [
    "complex_500_dataset.csv",
    "backend/data/complex_500_dataset.csv"
]

header = ["case_id", "date", "district", "crime_type", "accused_name", "co_accused_ids", "description"]

for path in output_paths:
    with open(path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    print(f"Successfully generated {len(rows)} complex rows to: {path}")

print("[SUCCESS] 500-row Deep-Complexity Dataset Generation Complete!")
