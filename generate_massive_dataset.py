import csv
import random
from datetime import datetime, timedelta

# Set seed for deterministic high-quality output
random.seed(42)

# Districts across Karnataka
DISTRICTS = [
    "Mysuru", "Bengaluru", "Mangaluru", "Hubballi", "Belagavi", 
    "Ballari", "Kalaburagi", "Shivamogga", "Tumakuru", "Udupi",
    "Dharwad", "Mandya", "Hassan", "Chikkamagaluru", "Bagalkot",
    "Vijayapura", "Raichur", "Bidar", "Koppal", "Gadag"
]

CRIME_TYPES = [
    "Burglary", "Extortion", "Robbery", "Arms Trafficking", "Cybercrime",
    "Money Laundering", "Narcotics", "Smuggling", "Assault", "Kidnapping",
    "Vehicle Theft", "Rioting", "Counterfeiting", "Fraud", "Murder", "Arson"
]

# Define 10 Sprawling Criminal Syndicates with specialized roles, locations, and MOs
SYNDICATES = [
    {
        "name": "Devaraja Urs Gold & Vault Syndicate",
        "primary_districts": ["Mysuru", "Mandya", "Hassan"],
        "crime_focus": ["Burglary", "Robbery", "Counterfeiting", "Arson"],
        "kingpin": "Raju Gowda",
        "members": ["Anand Verma", "Raghavendra 'Raghu'", "Shiva 'Gas'", "Balu 'Cheetah'", "Santhosh 'Oxy'", "Gowrish", "Suresha"],
        "mo_templates": [
            "Armed gang breached a commercial jewelry showroom on {location} at 02:15 AM using high-pressure oxy-acetylene cutters. Escaped with {amount} kg of gold ornaments in a stolen SUV bearing duplicate number plates.",
            "Co-conspirator in the {location} vault break-in. Apprehended at a hidden workshop while attempting to melt {amount} kg of stolen gold bars into untraceable bullion ingots.",
            "Raided a clandestine printing press inside an industrial shed producing high-quality fake currency notes of Rs 500 denomination used by syndicate operatives to settle debts.",
            "Set fire to a commercial warehouse near {location} after the business owner refused to pay extortion demands issued by the Raju Gowda leadership."
        ],
        "locations": ["Devaraja Urs Road", "Saraswathipuram", "Vijayanagar Industrial Area", "Mandya Highway Godowns"]
    },
    {
        "name": "Coastal Cyber Skimming & Hawala Network",
        "primary_districts": ["Mangaluru", "Udupi", "Hubballi"],
        "crime_focus": ["Cybercrime", "Money Laundering", "Counterfeiting", "Fraud"],
        "kingpin": "Zaid Khan",
        "members": ["Imran Pasha", "Rohan D'Souza", "Sameer 'Sam'", "Devdas Kamath", "Sanath", "Srinivas 'Tech'", "Rajat"],
        "mo_templates": [
            "Installed deep-insert ATM skimming devices and pinhole cameras across bank kiosks in {location}. Captured magnetic stripe data of over {count} customer accounts.",
            "Operated an extensive underground hawala transfer hub in {location}. Laundered Rs {amount} Crores generated from ATM skimming operations and offshore crypto routing.",
            "Technical engineer seized with {count} blank NFC-enabled debit cards. Confessed to cloning card dumps harvested via illegal skimming hardware across coastal districts.",
            "Operated an illicit SIM-box gateway in {location} converting international VOIP calls into local cellular numbers to mask syndicate cyber extortion communications."
        ],
        "locations": ["Hampankatta Commercial Hub", "Bunder Port Road", "Manipal University Road", "Malpe Harbor Kiosks"]
    },
    {
        "name": "Electronic City Synthetic Drug & Dark Web Cartel",
        "primary_districts": ["Bengaluru", "Mysuru", "Tumakuru"],
        "crime_focus": ["Narcotics", "Cybercrime", "Arms Trafficking", "Money Laundering"],
        "kingpin": "Karan 'Bhai' Sharma",
        "members": ["Naveen Raj", "Pooja Hegde", "Siddharth Mehta", "Ayesha 'Queen'", "Chandan Kumar", "Sunny 'DJ'", "Tenzin"],
        "mo_templates": [
            "Intercepted on {location} transporting {amount} kg of high-grade synthetic MDMA crystals concealed inside custom-built double-bottom compartments of a luxury vehicle.",
            "Coordinated mass phishing SMS bursts targeting net banking users across Karnataka. Utilized compromised mule credentials to layer funds into dark web crypto wallets.",
            "Chartered accountant arrested for registering shell companies across {location} to launder narcotics revenue and cryptocurrency payouts for the Karan Sharma network.",
            "Identified as a core distributor supplying synthetic ecstasy and cocaine packages to VIP nightlife patrons across {location}."
        ],
        "locations": ["Electronic City Phase 2", "Koramangala 4th Block", "Indiranagar 100ft Road", "HSR Layout Phase 1"]
    },
    {
        "name": "Ballari Iron Ore & Highway Extortion Gang",
        "primary_districts": ["Ballari", "Koppal", "Raichur"],
        "crime_focus": ["Extortion", "Assault", "Murder", "Smuggling"],
        "kingpin": "Reddy 'Dora'",
        "members": ["Veerabhadraappa", "Muni 'Rowdy'", "Kondaiah", "Sekhar", "Yellappa", "Giddaiah", "Basavanna", "Obalesh"],
        "mo_templates": [
            "Extorted heavy illegal transport levies from fleet operators carrying excavated iron ore across the {location} mining belt under explicit threat of armed intervention.",
            "Carried out brutal rod and club attacks against unionized truck drivers along {location} who refused to pay daily illegal highway extortion tolls.",
            "Intercepted near mining checkpost transporting {amount} tonnes of illegally excavated iron ore and red sanders timber with fabricated transit documents.",
            "Executed a targeted shooting of a rival transport contractor at a roadside dhaba near {location} to establish total monopoly over mining transport lines."
        ],
        "locations": ["Hospet Mining Belt", "Toranagallu Highway", "Sandur Iron Quarry Road", "Ballari APMC Yard"]
    },
    {
        "name": "Western Ghats Timber & Wildlife Poaching Ring",
        "primary_districts": ["Shivamogga", "Chikkamagaluru", "Hassan"],
        "crime_focus": ["Smuggling", "Assault", "Narcotics", "Vehicle Theft"],
        "kingpin": "Nagaraj 'Forest'",
        "members": ["Basavaraj Naik", "Harish 'Ganja'", "Manja 'Blade'", "Lokesh", "Gajendra", "Narasimha", "Dharma"],
        "mo_templates": [
            "Apprehended inside {location} reserve with {amount} kg of high-value red sanders logs and wildlife skins destined for coastal export hubs.",
            "Attacked forest guards during a midnight anti-poaching patrol near {location} using machetes and iron pipes, allowing the timber smuggling convoy to escape.",
            "Cultivated {count} acres of illegal cannabis crops hidden deep inside dense forest plantations near {location}. Distributed weed via timber transport trucks.",
            "Stole heavy-duty off-road tractors and winches from agricultural estates to drag felled contraband trees through difficult jungle terrain near {location}."
        ],
        "locations": ["Bhadra Wildlife Corridor", "Agumbe Forest Reserve", "Sakleshpur Timber Depot", "Mudigere Plantation Border"]
    },
    {
        "name": "Northern Border Arms Trafficking & Dacoity Syndicate",
        "primary_districts": ["Belagavi", "Kalaburagi", "Vijayapura", "Bidar"],
        "crime_focus": ["Arms Trafficking", "Robbery", "Burglary", "Rioting"],
        "kingpin": "Tariq Anwar",
        "members": ["Suresh Kumar", "Subhash 'Fauji'", "Sachin Shinde", "Ganesh 'Gunner'", "Bhimrao", "Ajay 'Border'", "Dattatreya"],
        "mo_templates": [
            "Seized at {location} border checkpoint while transporting {count} factory-made semi-automatic pistols and ammunition concealed inside hidden vehicle compartments.",
            "Intercepted a bullion transit vehicle on {location} using illegal firearms. Looted Rs {amount} Lakhs worth of silver ingots and cash bags.",
            "Arrested carrying country-made carbines and shotguns procured across the state border for distribution to southern crime syndicates operating in Bangalore and Mysuru.",
            "Extorted protection payments from limestone quarry owners near {location} threatening armed sabotage using weapons acquired from Subhash Fauji."
        ],
        "locations": ["Nipani Border Checkpost", "Pune-Bangalore Highway NH-4", "Shahapur Quarry Belt", "Bidar Railway Godowns"]
    },
    {
        "name": "Hubballi APMC & Cooperative Bank Robbery Crew",
        "primary_districts": ["Hubballi", "Dharwad", "Gadag"],
        "crime_focus": ["Burglary", "Extortion", "Rioting", "Assault"],
        "kingpin": "Santosh Patil",
        "members": ["Manjunath 'Sunil' Desai", "Prakash Jhadav", "Vinay 'Vinu'", "Ashok 'Auto' Mani", "Laxman 'Laxi'", "Ravi 'Rambo'", "Raghu 'Lock'"],
        "mo_templates": [
            "Nighttime break-in at a commercial cooperative bank branch in {location}. Alarm wiring disabled via insider blueprints; vault door breached via hydraulic spreaders.",
            "Demanded Rs {amount} Lakhs ransom from the bank branch manager threatening severe bodily harm unless CCTV DVR hard drives from the bank robbery were handed over.",
            "Incited violent mob disturbances in {location} commercial market area to divert police rapid action teams away from extortion cash drop-offs.",
            "Specialist locksmith who fabricated duplicate master keys and vault bypass tools utilized by Santosh Patil during commercial bank break-ins across {location}."
        ],
        "locations": ["Vidyanagar Bank Circle", "Hubballi APMC Market Yard", "Gokul Road Industrial Area", "Dharwad Court Road"]
    },
    {
        "name": "Silicon Valley Financial & Investment Scam Cartel",
        "primary_districts": ["Bengaluru", "Mysuru", "Tumakuru"],
        "crime_focus": ["Fraud", "Cybercrime", "Money Laundering", "Extortion"],
        "kingpin": "Divya Prakash",
        "members": ["Nitin 'Hacker'", "Deepa 'Mam'", "Ramesh Kulkarni", "Meghana", "Ananya 'CA'", "Tarun 'CA'", "Suhail"],
        "mo_templates": [
            "Engineered fraudulent investment trading APK applications. Tricked senior citizens across {location} into depositing over Rs {amount} Lakhs into compromised mule accounts.",
            "Dark web specialist who developed backend server infrastructure for fake lottery and KYC update scams. Hosted command servers on offshore bulletproof networks.",
            "Created {count} fraudulent bank accounts using forged biometric Aadhaar credentials. Accounts were utilized by cyber gangs to rapidly layer and withdraw cash.",
            "Supervised call center telecallers in {location} impersonating customs and police officials to extort money from victims under fake parcel seizure threats."
        ],
        "locations": ["Whitefield Tech Park Road", "Electronic City IT Corridor", "Marathahalli Bridge", "Jayanagar 9th Block"]
    },
    {
        "name": "Southern Marine Contraband & Gold Smuggling Ring",
        "primary_districts": ["Mangaluru", "Udupi", "Mysuru"],
        "crime_focus": ["Smuggling", "Money Laundering", "Assault", "Robbery"],
        "kingpin": "Abdul Khader",
        "members": ["Farooq 'Blade'", "John 'Captain'", "Rasheed 'Sultaan'", "Usman", "Kader 'Boat'", "Yusuf 'Seth'", "Ibrahim 'Press'"],
        "mo_templates": [
            "Fishing trawler captain intercepted off {location} while transferring {amount} kg of contraband red sanders logs and gold biscuits to international vessels.",
            "Contract enforcer carried out a severe blade assault against a customs intelligence officer near {location} investigating illegal marine cargo shipments.",
            "Senior associate in the hawala syndicate managing real estate front companies along {location} to absorb illicit cash inflows extorted from coastal traders.",
            "Couried hawala cash bags containing Rs {amount} Lakhs between {location} and Mumbai jewelry markets to settle trade imbalances generated by contraband exports."
        ],
        "locations": ["Old Port Bunder Harbor", "Ullal Beach Road", "Malpe Fishing Dock", "Surathkal Highway Checkpoint"]
    },
    {
        "name": "Central Karnataka Vehicle Chop-Shop & Getaway Network",
        "primary_districts": ["Mysuru", "Bengaluru", "Hubballi"],
        "crime_focus": ["Vehicle Theft", "Burglary", "Robbery", "Assault"],
        "kingpin": "Syed Ali",
        "members": ["Muralidhar", "Imran 'Bike'", "Farhan 'Auto'", "Salman", "Prashanth 'Pachhi'", "Karthik 'Katti'", "Somu 'Blade'"],
        "mo_templates": [
            "Stole high-performance sports motorcycles and luxury SUVs from hotel parking garages across {location}. Stolen vehicles were modified for syndicate robbery escapes.",
            "Operated a clandestine chop-shop in {location} dismantling stolen cargo vans and altering engine serial numbers to prevent detection during police inspections.",
            "Armed gang intercepted a wholesale diamond courier near {location}. Escaped on high-speed modified stolen motorcycles provided by Syed Ali after looting diamond rings.",
            "Enforcer executed a daylight attack against rival vehicle thieves near {location} to establish total monopoly over getaway vehicle supplies for commercial bank robbers."
        ],
        "locations": ["Gokulam Residential Area", "Peenya Industrial Sheds", "Jayalakshmipuram Ring Road", "Saraswathipuram Main Road"]
    }
]

# Generate exactly 1,000 rows (C3001 to C4000)
total_rows = 1000
start_id = 3001
start_date = datetime(2026, 1, 1)

rows = []
all_case_ids = [f"C{start_id + i}" for i in range(total_rows)]

# To create realistic cross-references, we map syndicates to their generated case IDs
syndicate_cases = {i: [] for i in range(len(SYNDICATES))}

for i in range(total_rows):
    case_id = f"C{start_id + i}"
    # Date progresses by 0 to 2 days per case across 2026-2028
    case_date = (start_date + timedelta(days=int(i * 0.65))).strftime("%Y-%m-%d")
    
    # Pick syndicate round-robin plus weighted randomization
    syn_idx = i % len(SYNDICATES)
    syn = SYNDICATES[syn_idx]
    syndicate_cases[syn_idx].append(case_id)
    
    district = random.choice(syn["primary_districts"])
    crime_type = random.choice(syn["crime_focus"])
    
    # Pick accused name (Kingpin roughly 15% of the time, members 85%)
    if random.random() < 0.15:
        accused_name = syn["kingpin"]
    else:
        accused_name = random.choice(syn["members"])
        
    # Generate co-accused IDs pointing to recent cases within the SAME syndicate (or adjacent syndicates)
    co_accused_list = []
    # Get recent cases from same syndicate
    recent_syn_cases = [cid for cid in syndicate_cases[syn_idx] if cid != case_id][-6:]
    if recent_syn_cases:
        num_co = random.randint(1, min(3, len(recent_syn_cases)))
        co_accused_list.extend(random.sample(recent_syn_cases, num_co))
    
    # 20% chance to link to an adjacent syndicate kingpin or case for inter-syndicate network clusters!
    if random.random() < 0.20 and i > 10:
        adj_idx = (syn_idx + random.choice([-1, 1])) % len(SYNDICATES)
        if syndicate_cases[adj_idx]:
            co_accused_list.append(random.choice(syndicate_cases[adj_idx][-4:]))
            
    co_accused_ids = ";".join(sorted(list(set(co_accused_list)))) if co_accused_list else f"C{start_id + max(0, i - random.randint(1, 5))}"
    
    # Construct sentence-format narrative description
    template = random.choice(syn["mo_templates"])
    location = random.choice(syn["locations"])
    amount = random.randint(15, 120)
    count = random.randint(40, 450)
    
    narrative_base = template.format(location=location, amount=amount, count=count)
    
    # Add forensic sentence details linking the accused and co_accused
    forensic_sentences = [
        f"Forensic examination confirmed call detail records linking {accused_name} directly to syndicate kingpin {syn['kingpin']}.",
        f"Investigators recovered digital ledger entries and encrypted burner SIM cards matching cross-referenced case files.",
        f"Ballistic and biometric samples collected from the scene positively correlate with operatives active across {district} district.",
        f"CCTV surveillance footage captured the suspect coordinating with co-accused operatives before fleeing along regional highway corridors.",
        f"Intelligence inputs confirm the operation was financed using layered cryptocurrency transactions and underground hawala channels."
    ]
    
    full_description = f"{narrative_base} {random.choice(forensic_sentences)}"
    
    rows.append([case_id, case_date, district, crime_type, accused_name, co_accused_ids, full_description])

# Write to both locations
paths = [
    "massive_realworld_syndicates.csv",
    "backend/data/massive_realworld_syndicates.csv"
]

header = ["case_id", "date", "district", "crime_type", "accused_name", "co_accused_ids", "description"]

for path in paths:
    with open(path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    print(f"Successfully wrote {len(rows)} records to {path}")

print("Dataset generation complete!")
