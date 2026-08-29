# --- MASTER TAXONOMY (Derived from your PDF) ---
MASTER_TAXONOMY = {
    "Agriculture, Forestry, Fishing, Food and Tobacco": [
        "Agriculture and Crop production",
        "Animal production, hunting",
        "Fishing",
        "Food, drink and beverages",
        "Forestry and logging",
        "Tobacco"
    ],
    "Automotive, Motor Vehicles, Machinery and Transportation": [
        "Aeronautics & Aerospace",
        "Automotive & Auto Parts",
        "Aviation & Airlines",
        "Construction & Heavy Equipment",
        "Industrial Machinery & Equipment",
        "Fluid Control & Hydraulics",
        "Railway",
        "Ships and shipbuilding",
        "Transport and storage of goods"
    ],
    "Business Services, Retail and Commerce": [
        "Business administration and management",
        "Consulting & HR",
        "Retail, eTail, eCommerce, Wholesale",
        "Translation & Document Services",
        "Security Services"
    ],
    "Chemistry": [
        "Agrochemicals",
        "Basic and Intermediate Chemical Manufacturing",
        "Paints, Coatings & Finishing",
        "Plastics & Fibers"
    ],
    "Computing Hardware": [
        "Computers (Servers, Desktops, Laptops)",
        "Components & Microprocessors",
        "Networking & Telecommunications Hardware",
        "Storage Devices",
        "Industrial & Military Systems"
    ],
    "Computing Software": [
        "Enterprise Resource Planning (ERP)",
        "Customer Relationship Management (CRM)",
        "Cybersecurity & Antivirus",
        "Database & Cloud Computing",
        "AI, Virtualization & Utilities",
        "Mobile & Web Applications",
        "Video Games & Interactive Entertainment"
    ],
    "Construction": [
        "Construction & Design Services",
        "Construction Materials",
        "Real Estate & Architecture"
    ],
    "Electronics": [
        "Consumer Electronics (TV, Audio, Mobile)",
        "Semiconductors & Circuits",
        "Automation & Robotics",
        "Telecommunications Equipment",
        "Electrical Engineering"
    ],
    "Energy, Water, and Utilities": [
        "Oil & Gas (Extraction & Processing)",
        "Alternative & Renewable Energies (Solar, Wind, Biofuel)",
        "Electric Utilities & Power Generation",
        "Nuclear Energy",
        "Water Supply & Treatment"
    ],
    "Environment, Ecology, Waste, Hazard": [
        "Environmental Science",
        "Waste Management",
        "Ecology & Conservation"
    ],
    "Financials": [
        "Banking, Lending & Asset Management",
        "Corporate Finance, M&A & Investment",
        "Insurance",
        "Accounting, Taxation & Audit",
        "FinTech & Crypto"
    ],
    "Gaming": [
        "Console & PC Gaming",
        "Mobile Gaming",
        "Casino & Gambling",
        "Esports"
    ],
    "Government & Public Sector": [
        "National, Regional & Local Government",
        "International Organizations (EU, UN, NGO)",
        "Policy & Standards"
    ],
    "Health care and Life Sciences": [
        "Medical Devices & Equipment",
        "Pharmaceuticals & Biotech",
        "Clinical Trials & Research",
        "Healthcare Services & Hospitals",
        "Veterinary Medicine",
        "Genetics & Biology"
    ],
    "Legal & Law": [
        "Corporate & Commercial Law",
        "Intellectual Property & Patents",
        "Litigation & Arbitration",
        "Contract Law",
        "Criminal & Family Law"
    ],
    "Media, Advertising & Marketing": [
        "Advertising, Branding & Marketing",
        "Film, TV & Video Production",
        "Publishing & Journalism",
        "Digital Media & Content"
    ],
    "Military & Defense": [
        "Land, Naval & Air Defense",
        "Firearms & Ammunition",
        "Missiles & Aerospace Defense"
    ],
    "Mining, Minerals and Metallurgy": [
        "Mining (Coal, Metal, Minerals)",
        "Metallurgy (Steel, Aluminum)",
        "Oil & Gas Extraction (Upstream)"
    ],
    "Telecommunication": [
        "Wireless & Satellite Services",
        "Internet & Data Services",
        "Infrastructure & Networking"
    ],
    "Textile, Clothing & Fashion": [
        "Fashion & Apparel",
        "Textile Manufacturing",
        "Luxury Goods"
    ],
    "Travel, Tourism & Arts": [
        "Hotels & Hospitality",
        "Travel & Tourism",
        "Arts, History & Culture",
        "Museums & Exhibitions"
    ]
}

# --- PRICING ENGINE (Mapped to Top-Level Categories) ---
# Base is 1.0. Higher means more expensive.
CATEGORY_PRICING = {
    "Health care and Life Sciences": 1.50,  # High Liability/Expertise
    "Legal & Law": 1.45,                    # High Liability/Precision
    "Chemistry": 1.35,                      # Technical Specialty
    "Financials": 1.30,                     # High Precision
    "Computing Software": 1.25,             # Technical Context
    "Computing Hardware": 1.25,             # Technical Context
    "Energy, Water, and Utilities": 1.25,   # Technical/Safety
    "Military & Defense": 1.25,             # Niche Terminology
    "Electronics": 1.20,                    # Technical
    "Mining, Minerals and Metallurgy": 1.20,# Technical
    "Automotive, Motor Vehicles, Machinery and Transportation": 1.15,
    "Telecommunication": 1.15,
    "Construction": 1.10,
    "Environment, Ecology, Waste, Hazard": 1.10,
    "Government & Public Sector": 1.10,
    "Media, Advertising & Marketing": 1.20, # Creative Surcharge (Transcreation)
    "Business Services, Retail and Commerce": 1.00,
    "Gaming": 1.10,                         # Creative/Slang
    "Textile, Clothing & Fashion": 1.15,    # Creative
    "Travel, Tourism & Arts": 1.00,
    "Agriculture, Forestry, Fishing, Food and Tobacco": 1.00,
    "Miscellaneous": 1.00
}

def calculate_blended_price_factor(domain_breakdown: list, difficulty_score: int, has_dtp_risk: bool):
    """
    Calculates price factor based on the New Taxonomy.
    """
    weighted_base = 0.0
    total_percent = 0
    
    for item in domain_breakdown:
        # The LLM will now output "Category > SubCategory"
        # We only need the Category (Left side of the >) for pricing
        full_string = item.get('domain', '')
        top_category = full_string.split('>')[0].strip()
        
        pct = item.get('percentage', 0)
        
        # Exact Match Lookup
        coef = CATEGORY_PRICING.get(top_category, 1.0)
        
        # Fallback: Partial match if LLM creates a slight variation
        if top_category not in CATEGORY_PRICING:
            for key, val in CATEGORY_PRICING.items():
                if key in top_category or top_category in key:
                    coef = val
                    break
        
        weighted_base += coef * (pct / 100.0)
        total_percent += pct
        
    if total_percent == 0: weighted_base = 1.0
    
    # Difficulty Multiplier (0.8 to 1.3 range)
    diff_mult = 1.0
    if difficulty_score <= 3: diff_mult = 0.90
    elif difficulty_score >= 8: diff_mult = 1.25
    elif difficulty_score >= 9: diff_mult = 1.35
    
    # DTP Surcharge (Layout Work)
    dtp_surcharge = 0.15 if has_dtp_risk else 0.0
    
    final_factor = (weighted_base * diff_mult) + dtp_surcharge
    return round(final_factor, 2), round(weighted_base, 2)