from __future__ import annotations

import json
from typing import Any


PRODUCTS: list[dict[str, Any]] = [
    {
        "sku": "EQUIP-CHAIR-500",
        "title": "A-dec 500 Operatory Package",
        "category": "equipment",
        "description": "Primary operatory chair package with assistant instrumentation and lighting.",
        "unit_price": 26000.0,
        "financing_eligible": True,
        "default_quantity": 1,
        "bundle_tags": ["operatory", "expansion", "chair"],
        "doc_source": "operatory-expansion-playbook.md",
    },
    {
        "sku": "IMAG-CBCT-210",
        "title": "Vatech CBCT Imaging Starter",
        "category": "imaging",
        "description": "3D imaging starter package for growth practices that need chairside diagnostics.",
        "unit_price": 18500.0,
        "financing_eligible": True,
        "default_quantity": 1,
        "bundle_tags": ["operatory", "expansion", "imaging"],
        "doc_source": "imaging-upgrade-guide.md",
    },
    {
        "sku": "STERI-M11-90",
        "title": "Midmark M11 Sterilization Suite",
        "category": "sterilization",
        "description": "Sterilization workflow bundle with autoclave and packaging starter supplies.",
        "unit_price": 7800.0,
        "financing_eligible": True,
        "default_quantity": 1,
        "bundle_tags": ["operatory", "sterilization", "compliance"],
        "doc_source": "operatory-expansion-playbook.md",
    },
    {
        "sku": "SUPPLY-START-050",
        "title": "Operatory Consumables Starter Kit",
        "category": "consumables",
        "description": "Initial stocking kit for barriers, cotton products, suction tips, and composites.",
        "unit_price": 2400.0,
        "financing_eligible": False,
        "default_quantity": 1,
        "bundle_tags": ["operatory", "consumables", "reorder"],
        "doc_source": "software-onboarding-and-adoption.md",
    },
    {
        "sku": "SOFT-PRACTICE-12",
        "title": "Cloud Practice Management Growth Bundle",
        "category": "software",
        "description": "Cloud practice-management bundle with imaging workflow hooks and analytics starter package.",
        "unit_price": 6240.0,
        "financing_eligible": False,
        "default_quantity": 1,
        "bundle_tags": ["software", "operatory", "imaging"],
        "doc_source": "software-onboarding-and-adoption.md",
    },
    {
        "sku": "SERV-ONBOARD-01",
        "title": "Digital Workflow Onboarding",
        "category": "services",
        "description": "Remote onboarding package for software, imaging workflow setup, and seller handoff.",
        "unit_price": 1800.0,
        "financing_eligible": False,
        "default_quantity": 1,
        "bundle_tags": ["software", "services", "onboarding"],
        "doc_source": "software-onboarding-and-adoption.md",
    },
    {
        "sku": "SERV-INSTALL-01",
        "title": "Equipment Installation & Setup",
        "category": "services",
        "description": "On-site delivery, installation, calibration, and setup of operatory and imaging equipment.",
        "unit_price": 1450.0,
        "financing_eligible": False,
        "default_quantity": 1,
        "bundle_tags": ["services", "installation", "setup", "operatory", "imaging", "onboarding"],
        "doc_source": "operatory-expansion-playbook.md",
    },
    {
        "sku": "SUPPORT-CARE-12",
        "title": "Equipment Care · Operatory Care",
        "category": "services",
        "description": "Equipment Care extended warranty for operatory equipment (chairs, delivery units).",
        "unit_price": 1600.0,
        "financing_eligible": False,
        "default_quantity": 1,
        "bundle_tags": ["services", "operatory", "equipment-care"],
        "doc_source": "financing-and-approval-guide.md",
    },
    {
        "sku": "SUPPORT-CARE-IMG",
        "title": "Equipment Care · Imaging Care",
        "category": "services",
        "description": "Equipment Care extended warranty for imaging equipment (CBCT, sensors, scanners).",
        "unit_price": 2100.0,
        "financing_eligible": False,
        "default_quantity": 1,
        "bundle_tags": ["services", "imaging", "equipment-care"],
        "doc_source": "financing-and-approval-guide.md",
    },
    {
        "sku": "SUPPORT-CARE-STER",
        "title": "Equipment Care · Sterilization Care",
        "category": "services",
        "description": "Equipment Care extended warranty for sterilization equipment (autoclaves).",
        "unit_price": 520.0,
        "financing_eligible": False,
        "default_quantity": 1,
        "bundle_tags": ["services", "sterilization", "equipment-care"],
        "doc_source": "financing-and-approval-guide.md",
    },
    {
        "sku": "SENSOR-IO-20",
        "title": "Intraoral Sensor Kit",
        "category": "imaging",
        "description": "Chairside sensor kit that extends existing imaging workflows into new operatories.",
        "unit_price": 4800.0,
        "financing_eligible": True,
        "default_quantity": 1,
        "bundle_tags": ["imaging", "operatory", "upgrade"],
        "doc_source": "imaging-upgrade-guide.md",
    },
    {
        "sku": "SCANNER-CHAIR-01",
        "title": "Chairside Scanner Bundle",
        "category": "imaging",
        "description": "Scanner bundle for restorative workflows that pairs with cloud software and imaging support.",
        "unit_price": 13900.0,
        "financing_eligible": True,
        "default_quantity": 1,
        "bundle_tags": ["imaging", "upgrade", "restorative"],
        "doc_source": "imaging-upgrade-guide.md",
    },
    {
        "sku": "REORDER-GLOVE-24",
        "title": "Exam Gloves Case Pack",
        "category": "consumables",
        "description": "High-velocity consumable reorder pack for general practices and DSO sites.",
        "unit_price": 190.0,
        "financing_eligible": False,
        "default_quantity": 6,
        "bundle_tags": ["reorder", "consumables"],
        "doc_source": "operatory-expansion-playbook.md",
    },
    {
        "sku": "REORDER-ANES-10",
        "title": "Local Anesthetic Bundle",
        "category": "consumables",
        "description": "Bundled reorder of common anesthetic and accessory stock for busy operatories.",
        "unit_price": 320.0,
        "financing_eligible": False,
        "default_quantity": 4,
        "bundle_tags": ["reorder", "consumables"],
        "doc_source": "operatory-expansion-playbook.md",
    },
    {
        "sku": "EQUIP-DELIVERY-300",
        "title": "Operatory Delivery Unit",
        "category": "equipment",
        "description": "Doctor and assistant delivery system with integrated handpiece controls for a new operatory.",
        "unit_price": 9400.0,
        "financing_eligible": True,
        "default_quantity": 1,
        "bundle_tags": ["operatory", "expansion", "equipment"],
        "doc_source": "operatory-expansion-playbook.md",
    },
    {
        "sku": "EQUIP-COMPRESS-200",
        "title": "Dental Compressor & Vacuum System",
        "category": "equipment",
        "description": "Oil-free compressor and dry vacuum utility package sized for a multi-operatory practice.",
        "unit_price": 6800.0,
        "financing_eligible": True,
        "default_quantity": 1,
        "bundle_tags": ["operatory", "equipment", "utility"],
        "doc_source": "operatory-expansion-playbook.md",
    },
    {
        "sku": "EQUIP-CABINET-150",
        "title": "Operatory Cabinetry Set",
        "category": "equipment",
        "description": "Treatment-room cabinetry set with sterilization-center casework for an expansion build-out.",
        "unit_price": 5400.0,
        "financing_eligible": True,
        "default_quantity": 1,
        "bundle_tags": ["operatory", "expansion", "equipment"],
        "doc_source": "operatory-expansion-playbook.md",
    },
    {
        "sku": "IMAG-PANO-120",
        "title": "Planmeca Panoramic X-ray System",
        "category": "imaging",
        "description": "2D panoramic imaging system for practices that need broad diagnostics without full CBCT.",
        "unit_price": 11200.0,
        "financing_eligible": True,
        "default_quantity": 1,
        "bundle_tags": ["imaging", "upgrade", "diagnostic"],
        "doc_source": "imaging-upgrade-guide.md",
    },
    {
        "sku": "IMAG-CAMERA-15",
        "title": "Intraoral Camera Kit",
        "category": "imaging",
        "description": "Chairside intraoral camera kit for patient education and case acceptance.",
        "unit_price": 1950.0,
        "financing_eligible": False,
        "default_quantity": 1,
        "bundle_tags": ["imaging", "upgrade", "operatory"],
        "doc_source": "imaging-upgrade-guide.md",
    },
    {
        "sku": "STERI-WASH-40",
        "title": "Instrument Washer-Disinfector",
        "category": "sterilization",
        "description": "Automated instrument washer-disinfector that adds throughput and compliance to the sterilization center.",
        "unit_price": 9200.0,
        "financing_eligible": True,
        "default_quantity": 1,
        "bundle_tags": ["sterilization", "compliance", "operatory"],
        "doc_source": "operatory-expansion-playbook.md",
    },
    {
        "sku": "SUPPLY-RESTOR-070",
        "title": "Restorative Materials Starter Kit",
        "category": "consumables",
        "description": "Composite, bonding, and finishing material starter kit for restorative workflows.",
        "unit_price": 1750.0,
        "financing_eligible": False,
        "default_quantity": 1,
        "bundle_tags": ["consumables", "reorder", "restorative"],
        "doc_source": "operatory-expansion-playbook.md",
    },
    {
        "sku": "SOFT-ENGAGE-12",
        "title": "Patient Engagement Suite",
        "category": "software",
        "description": "Online scheduling, reminders, and patient messaging add-on that layers onto the practice-management system.",
        "unit_price": 3600.0,
        "financing_eligible": False,
        "default_quantity": 1,
        "bundle_tags": ["software", "engagement", "growth"],
        "doc_source": "software-onboarding-and-adoption.md",
    },
    {
        "sku": "SOFT-ANALYTICS-12",
        "title": "Practice Analytics Add-on",
        "category": "software",
        "description": "Production, hygiene, and recall analytics dashboards for the cloud practice-management bundle.",
        "unit_price": 2880.0,
        "financing_eligible": False,
        "default_quantity": 1,
        "bundle_tags": ["software", "analytics", "growth"],
        "doc_source": "software-onboarding-and-adoption.md",
    },
    {
        "sku": "SERV-TRAIN-02",
        "title": "On-site Clinical Training",
        "category": "services",
        "description": "On-site clinical and workflow training day for new equipment and software adoption.",
        "unit_price": 2200.0,
        "financing_eligible": False,
        "default_quantity": 1,
        "bundle_tags": ["services", "onboarding", "training"],
        "doc_source": "software-onboarding-and-adoption.md",
    },
    {
        "sku": "EQUIP-LIGHT-LED-210",
        "title": "LED Operatory Light",
        "category": "equipment",
        "description": "Ceiling-mounted LED treatment light with touch-free controls for a new or refreshed operatory.",
        "unit_price": 4850.0,
        "financing_eligible": True,
        "default_quantity": 1,
        "bundle_tags": ["equipment", "operatory", "expansion", "lighting"],
        "doc_source": "operatory-expansion-playbook.md",
    },
    {
        "sku": "EQUIP-HANDPIECE-240",
        "title": "Electric Handpiece System",
        "category": "equipment",
        "description": "Electric motor and handpiece set for restorative, crown, and bridge procedures.",
        "unit_price": 3950.0,
        "financing_eligible": True,
        "default_quantity": 1,
        "bundle_tags": ["equipment", "operatory", "restorative", "handpiece"],
        "doc_source": "operatory-expansion-playbook.md",
    },
    {
        "sku": "IMAG-PSP-070",
        "title": "Phosphor Plate Imaging Scanner",
        "category": "imaging",
        "description": "Compact phosphor-plate scanner for practices moving from film to reusable digital plates.",
        "unit_price": 8750.0,
        "financing_eligible": True,
        "default_quantity": 1,
        "bundle_tags": ["imaging", "digital", "upgrade", "intraoral"],
        "doc_source": "imaging-upgrade-guide.md",
    },
    {
        "sku": "IMAG-CEPH-140",
        "title": "Cephalometric Imaging Upgrade",
        "category": "imaging",
        "description": "Cephalometric imaging module for orthodontic analysis and treatment planning workflows.",
        "unit_price": 14600.0,
        "financing_eligible": True,
        "default_quantity": 1,
        "bundle_tags": ["imaging", "orthodontics", "upgrade", "diagnostic"],
        "doc_source": "imaging-upgrade-guide.md",
    },
    {
        "sku": "STERI-ULTRA-025",
        "title": "Ultrasonic Instrument Cleaner",
        "category": "sterilization",
        "description": "Countertop ultrasonic cleaner for consistent instrument pre-cleaning before sterilization.",
        "unit_price": 2350.0,
        "financing_eligible": False,
        "default_quantity": 1,
        "bundle_tags": ["sterilization", "compliance", "instrument-processing"],
        "doc_source": "operatory-expansion-playbook.md",
    },
    {
        "sku": "SUPPLY-ENDO-080",
        "title": "Endodontic Procedure Starter Kit",
        "category": "consumables",
        "description": "Starter assortment of files, irrigation supplies, paper points, and obturation accessories.",
        "unit_price": 980.0,
        "financing_eligible": False,
        "default_quantity": 1,
        "bundle_tags": ["consumables", "endodontics", "reorder", "procedure-kit"],
        "doc_source": "operatory-expansion-playbook.md",
    },
    {
        "sku": "SOFT-RECALL-12",
        "title": "Recall & Reputation Management Add-on",
        "category": "software",
        "description": "Automated recall campaigns, review requests, and reputation reporting for growing practices.",
        "unit_price": 2640.0,
        "financing_eligible": False,
        "default_quantity": 1,
        "bundle_tags": ["software", "engagement", "recall", "growth"],
        "doc_source": "software-onboarding-and-adoption.md",
    },
    {
        "sku": "SERV-MIGRATE-01",
        "title": "Practice Data Migration Service",
        "category": "services",
        "description": "Scoped migration and validation service for patient, schedule, and practice-management data.",
        "unit_price": 3200.0,
        "financing_eligible": False,
        "default_quantity": 1,
        "bundle_tags": ["services", "software", "migration", "onboarding"],
        "doc_source": "software-onboarding-and-adoption.md",
    },
    {
        "sku": "FINANCE-LEASE-36",
        "title": "36-Month Equipment Financing",
        "category": "financing",
        "description": "Financing placeholder line used in the quote narrative when capital purchases exceed budget thresholds.",
        "unit_price": 0.0,
        "financing_eligible": False,
        "default_quantity": 1,
        "bundle_tags": ["financing", "operatory", "imaging"],
        "doc_source": "financing-and-approval-guide.md",
    },
]

ACCOUNTS: list[dict[str, Any]] = [
    {
        "account_id": "acct-riverfront",
        "erp_customer_id": "ERP-100482",
        "salesforce_account_id": "001RF0001482",
        "name": "Riverfront Dental Group",
        "segment": "mid-market",
        "specialty": "general dentistry",
        "growth_stage": "expanding",
        "region": "Northeast",
        "rep_code": "EQ-NE-17",
        "installed_base": ["SOFT-PRACTICE-12", "SENSOR-IO-20", "EQUIP-CHAIR-500", "SUPPLY-START-050"],
        "chair_count": 4,
        "num_locations": 1,
        "annual_spend_usd": 148_000,
        "days_since_last_purchase": 12,
    },
    {
        "account_id": "acct-lakeside",
        "erp_customer_id": "ERP-100905",
        "salesforce_account_id": "001LS0001905",
        "name": "Lakeside Pediatric Dental",
        "segment": "growth",
        "specialty": "pediatric dentistry",
        "growth_stage": "adding chairs",
        "region": "Central",
        "rep_code": "EQ-CN-09",
        "installed_base": ["SOFT-PRACTICE-12", "IMAG-CAMERA-15", "REORDER-ANES-10"],
        "chair_count": 2,
        "num_locations": 1,
        "annual_spend_usd": 62_000,
        "days_since_last_purchase": 29,
    },
    {
        "account_id": "acct-orchard",
        "erp_customer_id": "ERP-101224",
        "salesforce_account_id": "001OS0001224",
        "name": "Orchard Specialty Center",
        "segment": "enterprise",
        "specialty": "endodontics",
        "growth_stage": "refreshing imaging",
        "region": "West",
        "rep_code": "EQ-WE-22",
        "installed_base": ["IMAG-CBCT-210", "SUPPORT-CARE-12", "STERI-M11-90", "REORDER-GLOVE-24"],
        "chair_count": 3,
        "num_locations": 1,
        "annual_spend_usd": 210_000,
        "days_since_last_purchase": 74,
    },
    {
        "account_id": "acct-summit",
        "erp_customer_id": "ERP-101687",
        "salesforce_account_id": "001SM0001687",
        "name": "Summit Oral Surgery Center",
        "segment": "mid-market",
        "specialty": "oral surgery",
        "growth_stage": "expanding",
        "region": "Southwest",
        "rep_code": "EQ-SW-31",
        "installed_base": ["IMAG-CBCT-210", "STERI-M11-90", "EQUIP-CHAIR-500", "EQUIP-DELIVERY-300"],
        "chair_count": 5,
        "num_locations": 1,
        "annual_spend_usd": 185_000,
        "days_since_last_purchase": 41,
    },
    {
        "account_id": "acct-brightsmile",
        "erp_customer_id": "ERP-101903",
        "salesforce_account_id": "001BS0001903",
        "name": "BrightSmile Orthodontics",
        "segment": "growth",
        "specialty": "orthodontics",
        "growth_stage": "adding chairs",
        "region": "Southeast",
        "rep_code": "EQ-SE-08",
        "installed_base": ["SCANNER-CHAIR-01", "SOFT-PRACTICE-12", "SENSOR-IO-20"],
        "chair_count": 3,
        "num_locations": 2,
        "annual_spend_usd": 97_000,
        "days_since_last_purchase": 33,
    },
    {
        "account_id": "acct-meridian",
        "erp_customer_id": "ERP-102245",
        "salesforce_account_id": "001MD0002245",
        "name": "Meridian Dental Partners",
        "segment": "enterprise",
        "specialty": "multi-location DSO",
        "growth_stage": "refreshing imaging",
        "region": "Midwest",
        "rep_code": "EQ-MW-14",
        "installed_base": ["SOFT-PRACTICE-12", "REORDER-GLOVE-24", "SENSOR-IO-20", "IMAG-CBCT-210", "STERI-M11-90", "SUPPORT-CARE-12"],
        "chair_count": 8,
        "num_locations": 5,
        "annual_spend_usd": 520_000,
        "days_since_last_purchase": 8,
    },
    # --- New accounts ---
    {
        "account_id": "acct-cascade",
        "erp_customer_id": "ERP-102601",
        "salesforce_account_id": "001CA0002601",
        "name": "Cascade Family Dentistry",
        "segment": "growth",
        "specialty": "general dentistry",
        "growth_stage": "just starting",
        "region": "Northwest",
        "rep_code": "EQ-NW-03",
        "installed_base": ["EQUIP-CHAIR-500"],
        "chair_count": 2,
        "num_locations": 1,
        "annual_spend_usd": 38_000,
        "days_since_last_purchase": 97,
    },
    {
        "account_id": "acct-apex",
        "erp_customer_id": "ERP-102748",
        "salesforce_account_id": "001AP0002748",
        "name": "Apex Periodontics",
        "segment": "mid-market",
        "specialty": "periodontics",
        "growth_stage": "expanding",
        "region": "South",
        "rep_code": "EQ-SO-11",
        "installed_base": ["SENSOR-IO-20", "STERI-M11-90"],
        "chair_count": 3,
        "num_locations": 1,
        "annual_spend_usd": 122_000,
        "days_since_last_purchase": 55,
    },
    {
        "account_id": "acct-sunrise",
        "erp_customer_id": "ERP-102893",
        "salesforce_account_id": "001SR0002893",
        "name": "Sunrise Dental Studio",
        "segment": "growth",
        "specialty": "general dentistry",
        "growth_stage": "adding chairs",
        "region": "Central",
        "rep_code": "EQ-CN-19",
        "installed_base": ["SOFT-PRACTICE-12", "REORDER-GLOVE-24"],
        "chair_count": 3,
        "num_locations": 1,
        "annual_spend_usd": 71_000,
        "days_since_last_purchase": 18,
    },
    {
        "account_id": "acct-pacific",
        "erp_customer_id": "ERP-103041",
        "salesforce_account_id": "001PD0003041",
        "name": "Pacific DSO Group",
        "segment": "enterprise",
        "specialty": "multi-location DSO",
        "growth_stage": "refreshing imaging",
        "region": "West",
        "rep_code": "EQ-WE-07",
        "installed_base": ["SOFT-PRACTICE-12", "IMAG-CBCT-210", "SCANNER-CHAIR-01", "REORDER-GLOVE-24"],
        "chair_count": 18,
        "num_locations": 9,
        "annual_spend_usd": 890_000,
        "days_since_last_purchase": 5,
    },
    {
        "account_id": "acct-heartland",
        "erp_customer_id": "ERP-103188",
        "salesforce_account_id": "001HL0003188",
        "name": "Heartland Oral Health",
        "segment": "mid-market",
        "specialty": "general dentistry",
        "growth_stage": "expanding",
        "region": "Midwest",
        "rep_code": "EQ-MW-27",
        "installed_base": ["EQUIP-CHAIR-500", "SENSOR-IO-20"],
        "chair_count": 4,
        "num_locations": 1,
        "annual_spend_usd": 156_000,
        "days_since_last_purchase": 22,
    },
    {
        "account_id": "acct-coastal",
        "erp_customer_id": "ERP-103320",
        "salesforce_account_id": "001CE0003320",
        "name": "Coastal Endodontics",
        "segment": "mid-market",
        "specialty": "endodontics",
        "growth_stage": "refreshing imaging",
        "region": "Southeast",
        "rep_code": "EQ-SE-15",
        "installed_base": ["IMAG-CBCT-210", "SOFT-PRACTICE-12"],
        "chair_count": 3,
        "num_locations": 1,
        "annual_spend_usd": 108_000,
        "days_since_last_purchase": 63,
    },
    {
        "account_id": "acct-pinnacle",
        "erp_customer_id": "ERP-103467",
        "salesforce_account_id": "001PI0003467",
        "name": "Pinnacle Dental Arts",
        "segment": "growth",
        "specialty": "oral surgery",
        "growth_stage": "just starting",
        "region": "Southwest",
        "rep_code": "EQ-SW-44",
        "installed_base": ["STERI-M11-90"],
        "chair_count": 2,
        "num_locations": 1,
        "annual_spend_usd": 44_000,
        "days_since_last_purchase": 118,
    },
    {
        "account_id": "acct-northstar",
        "erp_customer_id": "ERP-103602",
        "salesforce_account_id": "001NK0003602",
        "name": "NorthStar Kids Dentistry",
        "segment": "growth",
        "specialty": "pediatric dentistry",
        "growth_stage": "adding chairs",
        "region": "Midwest",
        "rep_code": "EQ-MW-33",
        "installed_base": ["SOFT-PRACTICE-12", "REORDER-ANES-10"],
        "chair_count": 2,
        "num_locations": 2,
        "annual_spend_usd": 58_000,
        "days_since_last_purchase": 31,
    },
    {
        "account_id": "acct-grandvalley",
        "erp_customer_id": "ERP-103755",
        "salesforce_account_id": "001GV0003755",
        "name": "Grand Valley Dental",
        "segment": "enterprise",
        "specialty": "general dentistry",
        "growth_stage": "refreshing imaging",
        "region": "West",
        "rep_code": "EQ-WE-29",
        "installed_base": ["IMAG-CBCT-210", "EQUIP-CHAIR-500", "SUPPORT-CARE-12"],
        "chair_count": 6,
        "num_locations": 2,
        "annual_spend_usd": 275_000,
        "days_since_last_purchase": 47,
    },
    # Public organizations are searchable demo prospects only. Their names and
    # websites are verified from official public pages; no customer relationship,
    # installed base, purchasing history, or commercial values are asserted.
    {
        "account_id": "prospect-heartland-dental",
        "erp_customer_id": None,
        "salesforce_account_id": None,
        "name": "Heartland Dental",
        "segment": "enterprise",
        "specialty": "dental support organization",
        "growth_stage": "research prospect",
        "region": "National",
        "rep_code": "UNASSIGNED",
        "installed_base": [],
        "chair_count": None,
        "num_locations": None,
        "annual_spend_usd": None,
        "days_since_last_purchase": None,
        "demo_record": True,
        "account_record_type": "public_demo_prospect",
        "relationship_status": "demo_prospect_not_a_customer",
        "provenance_source": "official_website",
        "provenance_url": "https://heartland.com/",
        "provenance_verified_on": "2026-09-10",
    },
    {
        "account_id": "prospect-pds-health",
        "erp_customer_id": None,
        "salesforce_account_id": None,
        "name": "PDS Health",
        "segment": "enterprise",
        "specialty": "dental support organization",
        "growth_stage": "research prospect",
        "region": "National",
        "rep_code": "UNASSIGNED",
        "installed_base": [],
        "chair_count": None,
        "num_locations": None,
        "annual_spend_usd": None,
        "days_since_last_purchase": None,
        "demo_record": True,
        "account_record_type": "public_demo_prospect",
        "relationship_status": "demo_prospect_not_a_customer",
        "provenance_source": "official_website",
        "provenance_url": "https://www.pdshealth.com/",
        "provenance_verified_on": "2026-09-10",
    },
    {
        "account_id": "prospect-aspen-dental",
        "erp_customer_id": None,
        "salesforce_account_id": None,
        "name": "Aspen Dental",
        "segment": "enterprise",
        "specialty": "branded dental practice network",
        "growth_stage": "research prospect",
        "region": "National",
        "rep_code": "UNASSIGNED",
        "installed_base": [],
        "chair_count": None,
        "num_locations": None,
        "annual_spend_usd": None,
        "days_since_last_purchase": None,
        "demo_record": True,
        "account_record_type": "public_demo_prospect",
        "relationship_status": "demo_prospect_not_a_customer",
        "provenance_source": "official_website",
        "provenance_url": "https://www.aspendental.com/",
        "provenance_verified_on": "2026-09-10",
    },
    {
        "account_id": "prospect-dental-care-alliance",
        "erp_customer_id": None,
        "salesforce_account_id": None,
        "name": "Dental Care Alliance",
        "segment": "enterprise",
        "specialty": "dental support organization",
        "growth_stage": "research prospect",
        "region": "National",
        "rep_code": "UNASSIGNED",
        "installed_base": [],
        "chair_count": None,
        "num_locations": None,
        "annual_spend_usd": None,
        "days_since_last_purchase": None,
        "demo_record": True,
        "account_record_type": "public_demo_prospect",
        "relationship_status": "demo_prospect_not_a_customer",
        "provenance_source": "official_website",
        "provenance_url": "https://www.dentalcarealliance.net/",
        "provenance_verified_on": "2026-09-10",
    },
    {
        "account_id": "prospect-mb2-dental",
        "erp_customer_id": None,
        "salesforce_account_id": None,
        "name": "MB2 Dental",
        "segment": "enterprise",
        "specialty": "dental partnership organization",
        "growth_stage": "research prospect",
        "region": "National",
        "rep_code": "UNASSIGNED",
        "installed_base": [],
        "chair_count": None,
        "num_locations": None,
        "annual_spend_usd": None,
        "days_since_last_purchase": None,
        "demo_record": True,
        "account_record_type": "public_demo_prospect",
        "relationship_status": "demo_prospect_not_a_customer",
        "provenance_source": "official_website",
        "provenance_url": "https://mb2dental.com/",
        "provenance_verified_on": "2026-09-10",
    },
]

# Keep every account visibly bounded as demo data when consumed through Genie or
# the API. Existing fictional fixtures retain their IDs because history fixtures
# and regression tests depend on them.
for _account in ACCOUNTS:
    _account.setdefault("demo_record", True)
    _account.setdefault("account_record_type", "synthetic_demo_account")
    _account.setdefault("relationship_status", "synthetic_fixture_no_real_customer_assertion")
    _account.setdefault("provenance_source", "synthetic_fixture")
    _account.setdefault("provenance_url", None)
    _account.setdefault("provenance_verified_on", None)
del _account

PROMOTIONS: list[dict[str, Any]] = [
    {
        "promotion_id": "promo-op-10",
        "title": "Operatory Expansion Program",
        "category": "equipment",
        "description": "Bundle discount when chair, sterilization, and onboarding are quoted together.",
        "discount_pct": 8.0,
        "applies_to": "all",
    },
    {
        "promotion_id": "promo-imaging-6",
        "title": "Imaging Refresh",
        "category": "imaging",
        "description": "6 percent promotion when CBCT and care plan are quoted together.",
        "discount_pct": 6.0,
        "applies_to": "all",
    },
    {
        "promotion_id": "promo-dso-multi-10",
        "title": "DSO Multi-Location Equipment Deal",
        "category": "equipment",
        "description": "10 percent discount on equipment bundles for accounts with 3 or more locations.",
        "discount_pct": 10.0,
        "applies_to": "multi-location DSO",
    },
    {
        "promotion_id": "promo-ped-7",
        "title": "Pediatric Starter Bundle",
        "category": "consumables",
        "description": "7 percent off consumables and software starter kits for pediatric dentistry practices.",
        "discount_pct": 7.0,
        "applies_to": "pediatric dentistry",
    },
    {
        "promotion_id": "promo-migration-15",
        "title": "legacy CPQ Migration Incentive",
        "category": "software",
        "description": "15 percent off Cloud Practice Management Growth Bundle for practices migrating away from legacy CPQ quoting.",
        "discount_pct": 15.0,
        "applies_to": "all",
    },
    {
        "promotion_id": "promo-renewal-5",
        "title": "Care Plan Renewal",
        "category": "services",
        "description": "5 percent off Equipment Care Plan on renewal for accounts with existing Equipment Care coverage.",
        "discount_pct": 5.0,
        "applies_to": "renewal",
    },
]

SAMPLE_PROMPTS: list[str] = [
    "Build a CBCT quote for Riverfront with segment pricing and Equipment Care.",
    "Quote a two-operatory expansion under $80k and flag approvals.",
    "Prepare a customer-ready quote for Lakeside with Equipment Care.",
]

TABLE_NAMES: tuple[str, ...] = (
    "accounts",
    "products",
    "pricebook",
    "bundle_components",
    "account_history",
    "installed_base",
    "inventory",
    "promotions",
    "source_freshness",
    "equipment_order_history",
    "supplier_segment_pricing",
    "supplier_price_book",
    "legacy_quote_history",
    "quote_conversion_history",
    "approval_rules",
    "warranty_eligibility",
)

SEGMENT_DISCOUNT_PCT = {
    "growth": 3.0,
    "mid-market": 5.0,
    "enterprise": 8.0,
}

SOURCE_FRESHNESS: list[dict[str, Any]] = [
    {"source": "ERP", "status": "Fresh", "detail": "Customer and product master synced today."},
    {"source": "OMS", "status": "Fresh", "detail": "Equipment availability synced today."},
    {"source": "Legacy Quotes", "status": "Loaded", "detail": "Historical quotes are available for pricing context."},
    {"source": "Agentic CPQ", "status": "Ready", "detail": "Customer-ready PDF generation is available."},
]


def build_pricebook_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for product in PRODUCTS:
        rows.append(
            {
                "pricebook_id": "standard-us",
                "sku": product["sku"],
                "currency_code": "USD",
                "list_price": product["unit_price"],
                "recommended_price": recommended_price(product, "mid-market"),
                "supplier_cost": supplier_cost(product),
                "gross_margin_pct": gross_margin_pct(recommended_price(product, "mid-market"), supplier_cost(product)),
                "financing_eligible": product["financing_eligible"],
            }
        )
    return rows


# Supplier cost as a share of list price, by category. Hoisted to module level so
# derived lines (e.g. the Equipment Care care plan, a `services` line) can reuse the
# same ratio against their own scaled price instead of duplicating the number.
CATEGORY_COST_PCT = {
    "equipment": 0.71,
    "imaging": 0.68,
    "sterilization": 0.66,
    "software": 0.28,
    "services": 0.35,
    "consumables": 0.54,
    "financing": 0.0,
}


def supplier_cost(product: dict[str, Any]) -> float:
    return round(product["unit_price"] * CATEGORY_COST_PCT.get(product["category"], 0.62), 2)


# Synthetic gap between a single legacy wholesale cost and the segment- and
# volume-adjusted supplier cost used by the demo price check.
LEGACY_OVERPAY_PCT = {
    "equipment": 0.09,
    "imaging": 0.11,
    "sterilization": 0.08,
    "consumables": 0.04,
    "software": 0.0,
    "services": 0.0,
    "financing": 0.0,
}

# Synthetic annual order velocity used only to project per-quote price-check
# savings into an annualized run rate; the UI labels it as a projection.
ANNUAL_ORDER_VELOCITY = {
    "EQUIP-CHAIR-500": 480,
    "IMAG-CBCT-210": 300,
    "STERI-M11-90": 600,
    "SCANNER-CHAIR-01": 250,
    "SENSOR-IO-20": 700,
    "SUPPLY-START-050": 1500,
    "REORDER-GLOVE-24": 4200,
    "REORDER-ANES-10": 3100,
}

# Per-SKU order seeding for equipment_order_history: (number_of_orders, units_per_order).
# Drives realistic "sales volume" aggregations — consumables ship in bulk and high
# frequency, capital equipment ships in ones and twos. Independent of the run-rate
# headline (that derives only from ANNUAL_ORDER_VELOCITY in supplier_price_book).
ORDER_SEED: dict[str, tuple[int, int]] = {
    "REORDER-GLOVE-24": (6, 48),
    "REORDER-ANES-10": (5, 30),
    "SUPPLY-START-050": (5, 20),
    "SUPPLY-RESTOR-070": (4, 16),
    "SENSOR-IO-20": (5, 4),
    "IMAG-CAMERA-15": (4, 3),
    "SCANNER-CHAIR-01": (4, 2),
    "SUPPORT-CARE-12": (4, 1),
    "SOFT-PRACTICE-12": (3, 1),
    "SOFT-ENGAGE-12": (3, 1),
    "SOFT-ANALYTICS-12": (3, 1),
    "SERV-ONBOARD-01": (3, 1),
    "SERV-TRAIN-02": (3, 1),
    "STERI-M11-90": (4, 2),
    "STERI-WASH-40": (3, 1),
    "EQUIP-CHAIR-500": (4, 1),
    "EQUIP-DELIVERY-300": (3, 1),
    "EQUIP-COMPRESS-200": (3, 1),
    "EQUIP-CABINET-150": (3, 2),
    "IMAG-CBCT-210": (4, 1),
    "IMAG-PANO-120": (3, 1),
}

# Fixed date pool so generated order rows are deterministic across re-seeds.
_ORDER_DATES: tuple[str, ...] = (
    "2025-09-04", "2025-10-12", "2025-11-08", "2025-12-03", "2026-01-15",
    "2026-02-09", "2026-03-11", "2026-04-07", "2026-05-19", "2026-06-02",
)


def negotiated_cost(product: dict[str, Any]) -> float:
    """Segment- and volume-adjusted supplier cost for the distributor."""
    return supplier_cost(product)


def legacy_wholesale_cost(product: dict[str, Any]) -> float:
    """The single wholesale cost legacy CPQ would carry — higher than negotiated."""
    overpay_pct = LEGACY_OVERPAY_PCT.get(product["category"], 0.0)
    return round(negotiated_cost(product) * (1 + overpay_pct), 2)


def overpayment_for_line(sku: str, quantity: int = 1) -> dict[str, Any]:
    """Deterministic supplier-overpayment check for a single quote line.

    Returns the legacy cost legacy CPQ would have used, the correct negotiated
    cost, and the prevented overpayment (legacy - negotiated) * quantity.
    """
    product = next((item for item in PRODUCTS if item["sku"] == sku), None)
    if product is None:
        return {"legacy_cost": None, "correct_cost": None, "overpay_amount": 0.0}
    qty = max(1, int(quantity or 1))
    legacy = legacy_wholesale_cost(product)
    correct = negotiated_cost(product)
    return {
        "legacy_cost": legacy,
        "correct_cost": correct,
        "overpay_amount": round(max(legacy - correct, 0.0) * qty, 2),
    }


def build_supplier_price_book_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for product in PRODUCTS:
        correct = negotiated_cost(product)
        legacy = legacy_wholesale_cost(product)
        rows.append(
            {
                "sku": product["sku"],
                "category": product["category"],
                "legacy_wholesale_cost": legacy,
                "negotiated_cost": correct,
                "overpay_per_unit": round(max(legacy - correct, 0.0), 2),
                "annual_order_velocity": ANNUAL_ORDER_VELOCITY.get(product["sku"], 0),
            }
        )
    return rows


def overpay_runrate_projection() -> dict[str, Any]:
    """Annualize the per-unit price-check savings across equipment order velocity.

    Uses synthetic order velocity and reports a projection, not booked savings.
    """
    by_sku: list[dict[str, Any]] = []
    annual_total = 0.0
    for row in build_supplier_price_book_rows():
        units = row["annual_order_velocity"]
        if not units or row["overpay_per_unit"] <= 0:
            continue
        annualized = round(row["overpay_per_unit"] * units, 2)
        annual_total += annualized
        by_sku.append(
            {
                "sku": row["sku"],
                "overpay_per_unit": row["overpay_per_unit"],
                "annual_order_velocity": units,
                "annualized_overpay_prevented": annualized,
            }
        )
    by_sku.sort(key=lambda item: item["annualized_overpay_prevented"], reverse=True)
    return {
        "annualized_overpay_prevented": round(annual_total, 2),
        "basis": "Per-unit price-check delta applied to synthetic annual equipment order velocity.",
        "is_projection": True,
        "by_sku": by_sku,
    }


def recommended_price(product: dict[str, Any], segment: str) -> float:
    discount_pct = SEGMENT_DISCOUNT_PCT.get(segment, 4.0)
    if product["category"] in {"services", "software", "consumables", "financing"}:
        discount_pct = min(discount_pct, 2.0)
    return round(product["unit_price"] * (1 - discount_pct / 100), 2)


# Equipment Care (extended-warranty) plans. Each eligible equipment family maps to its
# own Equipment Care code, plan name, and rate. A real Care Plan is priced per covered
# equipment unit and scales with the equipment's value — not a flat fee — so the
# warranty on a $148k CBCT costs far more than the one on a $6k autoclave. The
# `care_plan_pct` is annual care as a share of the covered equipment's segment price.
# This dict is the canonical seed for the `warranty_eligibility` reference table; at
# runtime the app reads that table so codes/rates/eligibility are editable in data.
WARRANTY_PLANS: dict[str, dict[str, Any]] = {
    "equipment":     {"warranty_sku": "SUPPORT-CARE-12",   "warranty_title": "Equipment Care · Operatory Care",     "care_plan_pct": 0.10},
    "imaging":       {"warranty_sku": "SUPPORT-CARE-IMG",  "warranty_title": "Equipment Care · Imaging Care",       "care_plan_pct": 0.12},
    "sterilization": {"warranty_sku": "SUPPORT-CARE-STER", "warranty_title": "Equipment Care · Sterilization Care", "care_plan_pct": 0.08},
}

# The set of catalog SKUs that ARE Equipment Care plans (so they never spawn a plan of
# their own, and so the app can recognize a protection line regardless of source).
WARRANTY_SKUS = frozenset(plan["warranty_sku"] for plan in WARRANTY_PLANS.values())


def warranty_rules_from_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index warranty-eligibility rows by product SKU. Shared by the app (reading the
    Lakebase table) and the in-memory fallback (`build_warranty_eligibility_rows`)."""
    return {row["sku"]: row for row in rows if row.get("sku")}


def care_plan_eligible(sku: str, rules: dict[str, dict[str, Any]]) -> bool:
    """Whether ``sku`` carries an Equipment Care plan, per the resolved rules map."""
    return bool(rules.get(sku, {}).get("eligible"))


def care_plan_unit_price(product: dict[str, Any], segment: str, pct: float) -> float:
    """Equipment Care unit price for the given covered equipment, scaled to its value."""
    return round(recommended_price(product, segment) * pct, 2)


def care_plan_supplier_cost(unit_price: float) -> float:
    """Supplier cost for a care-plan line, using the shared `services` cost ratio."""
    return round(unit_price * CATEGORY_COST_PCT["services"], 2)


def gross_margin_pct(price: float, cost: float) -> float:
    if price <= 0:
        return 0.0
    return round(((price - cost) / price) * 100, 1)


def build_bundle_component_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    bundle_map = {
        "operatory-expansion": ["EQUIP-CHAIR-500", "STERI-M11-90", "SUPPLY-START-050", "SOFT-PRACTICE-12", "SERV-ONBOARD-01"],
        "imaging-refresh": ["IMAG-CBCT-210", "SENSOR-IO-20", "SUPPORT-CARE-12"],
        "consumables-reorder": ["REORDER-GLOVE-24", "REORDER-ANES-10"],
    }
    for bundle_id, skus in bundle_map.items():
        for sort_order, sku in enumerate(skus, start=1):
            rows.append(
                {
                    "bundle_id": bundle_id,
                    "bundle_name": bundle_id.replace("-", " ").title(),
                    "sku": sku,
                    "sort_order": sort_order,
                }
            )
    return rows


def build_account_history_rows() -> list[dict[str, Any]]:
    # reorder_cycle_days: how often this account reorders this SKU. NULL for one-time items.
    # Multiple rows per (account, sku) provide order-trend depth for Genie time-series queries.
    return [
        # --- Riverfront Dental Group ---
        {"account_id": "acct-riverfront",  "sku": "REORDER-GLOVE-24",  "last_order_date": "2026-04-12", "quantity": 8,  "reorder_cycle_days": 28},
        {"account_id": "acct-riverfront",  "sku": "REORDER-GLOVE-24",  "last_order_date": "2026-03-15", "quantity": 8,  "reorder_cycle_days": 28},
        {"account_id": "acct-riverfront",  "sku": "REORDER-GLOVE-24",  "last_order_date": "2026-02-14", "quantity": 6,  "reorder_cycle_days": 28},
        {"account_id": "acct-riverfront",  "sku": "REORDER-ANES-10",   "last_order_date": "2026-05-18", "quantity": 12, "reorder_cycle_days": 28},
        {"account_id": "acct-riverfront",  "sku": "REORDER-ANES-10",   "last_order_date": "2026-04-20", "quantity": 10, "reorder_cycle_days": 28},
        {"account_id": "acct-riverfront",  "sku": "REORDER-ANES-10",   "last_order_date": "2026-03-22", "quantity": 10, "reorder_cycle_days": 28},
        {"account_id": "acct-riverfront",  "sku": "SUPPLY-START-050",  "last_order_date": "2026-02-26", "quantity": 6,  "reorder_cycle_days": 60},
        {"account_id": "acct-riverfront",  "sku": "SUPPLY-START-050",  "last_order_date": "2025-12-28", "quantity": 5,  "reorder_cycle_days": 60},
        {"account_id": "acct-riverfront",  "sku": "SOFT-PRACTICE-12",    "last_order_date": "2026-01-08", "quantity": 1,  "reorder_cycle_days": None},
        # --- Lakeside Pediatric Dental ---
        {"account_id": "acct-lakeside",    "sku": "REORDER-ANES-10",   "last_order_date": "2026-05-03", "quantity": 4,  "reorder_cycle_days": 21},
        {"account_id": "acct-lakeside",    "sku": "REORDER-ANES-10",   "last_order_date": "2026-04-12", "quantity": 4,  "reorder_cycle_days": 21},
        {"account_id": "acct-lakeside",    "sku": "REORDER-ANES-10",   "last_order_date": "2026-03-22", "quantity": 3,  "reorder_cycle_days": 21},
        {"account_id": "acct-lakeside",    "sku": "REORDER-GLOVE-24",  "last_order_date": "2026-06-01", "quantity": 14, "reorder_cycle_days": 21},
        {"account_id": "acct-lakeside",    "sku": "REORDER-GLOVE-24",  "last_order_date": "2026-05-10", "quantity": 12, "reorder_cycle_days": 21},
        {"account_id": "acct-lakeside",    "sku": "SUPPLY-RESTOR-070", "last_order_date": "2026-04-19", "quantity": 5,  "reorder_cycle_days": 45},
        {"account_id": "acct-lakeside",    "sku": "SUPPLY-RESTOR-070", "last_order_date": "2026-03-05", "quantity": 4,  "reorder_cycle_days": 45},
        # --- Orchard Specialty Center ---
        {"account_id": "acct-orchard",     "sku": "REORDER-GLOVE-24",  "last_order_date": "2026-05-07", "quantity": 10, "reorder_cycle_days": 28},
        {"account_id": "acct-orchard",     "sku": "REORDER-GLOVE-24",  "last_order_date": "2026-04-09", "quantity": 10, "reorder_cycle_days": 28},
        {"account_id": "acct-orchard",     "sku": "REORDER-GLOVE-24",  "last_order_date": "2026-03-11", "quantity": 8,  "reorder_cycle_days": 28},
        {"account_id": "acct-orchard",     "sku": "SUPPORT-CARE-12",   "last_order_date": "2026-03-17", "quantity": 1,  "reorder_cycle_days": 365},
        {"account_id": "acct-orchard",     "sku": "SENSOR-IO-20",      "last_order_date": "2026-01-29", "quantity": 4,  "reorder_cycle_days": None},
        # --- Summit Oral Surgery Center ---
        {"account_id": "acct-summit",      "sku": "REORDER-GLOVE-24",  "last_order_date": "2026-05-10", "quantity": 6,  "reorder_cycle_days": 21},
        {"account_id": "acct-summit",      "sku": "REORDER-GLOVE-24",  "last_order_date": "2026-04-19", "quantity": 6,  "reorder_cycle_days": 21},
        {"account_id": "acct-summit",      "sku": "SUPPLY-START-050",  "last_order_date": "2026-04-03", "quantity": 9,  "reorder_cycle_days": 45},
        {"account_id": "acct-summit",      "sku": "SUPPLY-START-050",  "last_order_date": "2026-02-17", "quantity": 8,  "reorder_cycle_days": 45},
        {"account_id": "acct-summit",      "sku": "STERI-M11-90",      "last_order_date": "2026-02-20", "quantity": 1,  "reorder_cycle_days": None},
        # --- BrightSmile Orthodontics ---
        {"account_id": "acct-brightsmile", "sku": "REORDER-GLOVE-24",  "last_order_date": "2026-05-28", "quantity": 7,  "reorder_cycle_days": 28},
        {"account_id": "acct-brightsmile", "sku": "REORDER-GLOVE-24",  "last_order_date": "2026-04-30", "quantity": 7,  "reorder_cycle_days": 28},
        {"account_id": "acct-brightsmile", "sku": "REORDER-GLOVE-24",  "last_order_date": "2026-04-02", "quantity": 6,  "reorder_cycle_days": 28},
        {"account_id": "acct-brightsmile", "sku": "IMAG-CAMERA-15",    "last_order_date": "2026-03-22", "quantity": 2,  "reorder_cycle_days": None},
        {"account_id": "acct-brightsmile", "sku": "SCANNER-CHAIR-01",  "last_order_date": "2025-12-05", "quantity": 1,  "reorder_cycle_days": None},
        # --- Meridian Dental Partners ---
        {"account_id": "acct-meridian",    "sku": "REORDER-GLOVE-24",  "last_order_date": "2026-05-22", "quantity": 20, "reorder_cycle_days": 14},
        {"account_id": "acct-meridian",    "sku": "REORDER-GLOVE-24",  "last_order_date": "2026-05-08", "quantity": 20, "reorder_cycle_days": 14},
        {"account_id": "acct-meridian",    "sku": "REORDER-GLOVE-24",  "last_order_date": "2026-04-24", "quantity": 18, "reorder_cycle_days": 14},
        {"account_id": "acct-meridian",    "sku": "REORDER-GLOVE-24",  "last_order_date": "2026-04-10", "quantity": 20, "reorder_cycle_days": 14},
        {"account_id": "acct-meridian",    "sku": "REORDER-ANES-10",   "last_order_date": "2026-06-10", "quantity": 28, "reorder_cycle_days": 14},
        {"account_id": "acct-meridian",    "sku": "REORDER-ANES-10",   "last_order_date": "2026-05-27", "quantity": 28, "reorder_cycle_days": 14},
        {"account_id": "acct-meridian",    "sku": "SUPPLY-RESTOR-070", "last_order_date": "2026-04-30", "quantity": 16, "reorder_cycle_days": 30},
        {"account_id": "acct-meridian",    "sku": "SUPPLY-RESTOR-070", "last_order_date": "2026-03-31", "quantity": 14, "reorder_cycle_days": 30},
        {"account_id": "acct-meridian",    "sku": "SOFT-PRACTICE-12",    "last_order_date": "2026-03-01", "quantity": 3,  "reorder_cycle_days": None},
        # --- New accounts (1–2 rows each) ---
        {"account_id": "acct-cascade",    "sku": "REORDER-GLOVE-24",  "last_order_date": "2026-03-25", "quantity": 4,  "reorder_cycle_days": 28},
        {"account_id": "acct-apex",       "sku": "REORDER-GLOVE-24",  "last_order_date": "2026-05-14", "quantity": 5,  "reorder_cycle_days": 28},
        {"account_id": "acct-apex",       "sku": "SUPPLY-START-050",  "last_order_date": "2026-03-30", "quantity": 4,  "reorder_cycle_days": 60},
        {"account_id": "acct-sunrise",    "sku": "REORDER-GLOVE-24",  "last_order_date": "2026-06-10", "quantity": 6,  "reorder_cycle_days": 28},
        {"account_id": "acct-sunrise",    "sku": "REORDER-ANES-10",   "last_order_date": "2026-05-22", "quantity": 5,  "reorder_cycle_days": 28},
        {"account_id": "acct-pacific",    "sku": "REORDER-GLOVE-24",  "last_order_date": "2026-06-18", "quantity": 40, "reorder_cycle_days": 14},
        {"account_id": "acct-pacific",    "sku": "REORDER-ANES-10",   "last_order_date": "2026-06-18", "quantity": 50, "reorder_cycle_days": 14},
        {"account_id": "acct-pacific",    "sku": "SOFT-PRACTICE-12",    "last_order_date": "2026-01-15", "quantity": 9,  "reorder_cycle_days": None},
        {"account_id": "acct-heartland",  "sku": "REORDER-GLOVE-24",  "last_order_date": "2026-06-06", "quantity": 7,  "reorder_cycle_days": 28},
        {"account_id": "acct-heartland",  "sku": "SUPPLY-START-050",  "last_order_date": "2026-04-10", "quantity": 5,  "reorder_cycle_days": 60},
        {"account_id": "acct-coastal",    "sku": "REORDER-GLOVE-24",  "last_order_date": "2026-03-28", "quantity": 5,  "reorder_cycle_days": 28},
        {"account_id": "acct-coastal",    "sku": "SUPPLY-RESTOR-070", "last_order_date": "2026-02-14", "quantity": 4,  "reorder_cycle_days": 45},
        {"account_id": "acct-northstar",  "sku": "REORDER-ANES-10",   "last_order_date": "2026-05-29", "quantity": 5,  "reorder_cycle_days": 21},
        {"account_id": "acct-northstar",  "sku": "REORDER-GLOVE-24",  "last_order_date": "2026-05-29", "quantity": 8,  "reorder_cycle_days": 21},
        {"account_id": "acct-grandvalley","sku": "REORDER-GLOVE-24",  "last_order_date": "2026-05-12", "quantity": 12, "reorder_cycle_days": 28},
        {"account_id": "acct-grandvalley","sku": "SUPPORT-CARE-12",   "last_order_date": "2026-02-01", "quantity": 1,  "reorder_cycle_days": 365},
    ]

# Per-install metadata: install_year drives refresh opportunity; warranty_expires enables
# proactive renewal queries. Software and consumables have no warranty expiry.
_INSTALL_METADATA: dict[tuple[str, str], dict[str, Any]] = {
    # --- Original accounts ---
    ("acct-riverfront", "SOFT-PRACTICE-12"):    {"install_year": 2023, "warranty_expires": None},
    ("acct-riverfront", "SENSOR-IO-20"):      {"install_year": 2022, "warranty_expires": "2026-08-01"},
    ("acct-riverfront", "EQUIP-CHAIR-500"):   {"install_year": 2023, "warranty_expires": "2028-02-01"},
    ("acct-lakeside",   "SOFT-PRACTICE-12"):    {"install_year": 2024, "warranty_expires": None},
    ("acct-lakeside",   "IMAG-CAMERA-15"):    {"install_year": 2024, "warranty_expires": "2029-01-01"},
    ("acct-orchard",    "IMAG-CBCT-210"):     {"install_year": 2020, "warranty_expires": "2025-09-15"},
    ("acct-orchard",    "SUPPORT-CARE-12"):   {"install_year": 2021, "warranty_expires": None},
    ("acct-orchard",    "STERI-M11-90"):      {"install_year": 2022, "warranty_expires": "2027-01-01"},
    ("acct-summit",     "IMAG-CBCT-210"):     {"install_year": 2021, "warranty_expires": "2026-04-01"},
    ("acct-summit",     "STERI-M11-90"):      {"install_year": 2022, "warranty_expires": "2027-03-01"},
    ("acct-summit",     "EQUIP-CHAIR-500"):   {"install_year": 2022, "warranty_expires": "2027-02-01"},
    ("acct-summit",     "EQUIP-DELIVERY-300"):{"install_year": 2023, "warranty_expires": "2028-01-01"},
    ("acct-brightsmile","SCANNER-CHAIR-01"):  {"install_year": 2023, "warranty_expires": "2027-11-01"},
    ("acct-brightsmile","SENSOR-IO-20"):      {"install_year": 2023, "warranty_expires": "2028-04-01"},
    ("acct-meridian",   "SOFT-PRACTICE-12"):    {"install_year": 2022, "warranty_expires": None},
    ("acct-meridian",   "REORDER-GLOVE-24"):  {"install_year": 2023, "warranty_expires": None},
    ("acct-meridian",   "SENSOR-IO-20"):      {"install_year": 2021, "warranty_expires": "2025-11-01"},
    ("acct-meridian",   "IMAG-CBCT-210"):     {"install_year": 2022, "warranty_expires": "2027-01-01"},
    ("acct-meridian",   "STERI-M11-90"):      {"install_year": 2023, "warranty_expires": "2028-06-01"},
    # --- New accounts ---
    ("acct-cascade",    "EQUIP-CHAIR-500"):   {"install_year": 2024, "warranty_expires": "2029-01-01"},
    ("acct-apex",       "SENSOR-IO-20"):      {"install_year": 2023, "warranty_expires": "2027-06-01"},
    ("acct-apex",       "STERI-M11-90"):      {"install_year": 2022, "warranty_expires": "2026-12-01"},
    ("acct-pacific",    "IMAG-CBCT-210"):     {"install_year": 2022, "warranty_expires": "2026-10-01"},
    ("acct-pacific",    "SCANNER-CHAIR-01"):  {"install_year": 2023, "warranty_expires": "2028-01-01"},
    ("acct-heartland",  "EQUIP-CHAIR-500"):   {"install_year": 2023, "warranty_expires": "2028-03-01"},
    ("acct-heartland",  "SENSOR-IO-20"):      {"install_year": 2022, "warranty_expires": "2027-02-01"},
    ("acct-coastal",    "IMAG-CBCT-210"):     {"install_year": 2021, "warranty_expires": "2026-07-01"},
    ("acct-pinnacle",   "STERI-M11-90"):      {"install_year": 2024, "warranty_expires": "2029-04-01"},
    ("acct-grandvalley","IMAG-CBCT-210"):     {"install_year": 2020, "warranty_expires": "2025-06-01"},
    ("acct-grandvalley","EQUIP-CHAIR-500"):   {"install_year": 2023, "warranty_expires": "2028-07-01"},
}


def build_installed_base_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for account in ACCOUNTS:
        for sku in account["installed_base"]:
            meta = _INSTALL_METADATA.get((account["account_id"], sku), {"install_year": 2022, "warranty_expires": None})
            rows.append(
                {
                    "account_id": account["account_id"],
                    "sku": sku,
                    "status": "active",
                    "install_year": meta["install_year"],
                    "warranty_expires": meta["warranty_expires"],
                }
            )
    return rows


def build_inventory_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    inventory_defaults = {
        "equipment": (4, 14),
        "imaging": (6, 10),
        "sterilization": (8, 7),
        "services": (999, 0),
        "software": (999, 0),
        "consumables": (250, 2),
        "financing": (999, 0),
    }
    # Per-SKU overrides for demo realism (high-demand or constrained items)
    _overrides: dict[str, tuple[int, int]] = {
        "IMAG-CBCT-210":    (2, 21),   # scarce — long lead time
        "SCANNER-CHAIR-01": (1, 28),   # very scarce
        "STERI-M11-90":     (12, 5),   # well-stocked
    }
    for product in PRODUCTS:
        available_qty, lead_time_days = _overrides.get(product["sku"], inventory_defaults[product["category"]])
        rows.append(
            {
                "sku": product["sku"],
                "available_qty": available_qty,
                "lead_time_days": lead_time_days,
            }
        )
    return rows


def build_equipment_order_history_rows() -> list[dict[str, Any]]:
    """Generate a realistic order ledger with per-order quantities.

    Each SKU in ORDER_SEED produces several orders spread across accounts so that
    "sales volume" aggregations return believable, varied totals (consumables in the
    hundreds, capital equipment in the low single digits) instead of a flat 1.
    """
    rows: list[dict[str, Any]] = []
    # Public demo prospects have no claimed purchasing relationship and must not
    # be assigned generated orders. The synthetic fixture accounts continue to
    # drive the historical ledger used by the demo.
    account_ids = [
        account["account_id"]
        for account in ACCOUNTS
        if account["account_record_type"] == "synthetic_demo_account"
    ]
    order_no = 70010
    seq = 0
    # Iterate SKUs in PRODUCTS order so equipment/imaging/etc. interleave naturally.
    for product in PRODUCTS:
        seed = ORDER_SEED.get(product["sku"])
        if not seed:
            continue
        orders, units = seed
        for i in range(orders):
            account_id = account_ids[seq % len(account_ids)]
            order_date = _ORDER_DATES[seq % len(_ORDER_DATES)]
            # Vary quantity a little around the base unit so totals aren't perfectly flat.
            quantity = units + (i % 2 if units > 4 else 0)
            rows.append(
                {
                    "equipment_order_id": f"OMS-{order_no}",
                    "account_id": account_id,
                    "sku": product["sku"],
                    "quantity": quantity,
                    "status": "Installed" if i < orders - 1 else "In Transit",
                    "order_date": order_date,
                }
            )
            order_no += 13
            seq += 1
    return rows


def build_supplier_segment_pricing_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    segments = list(dict.fromkeys(account["segment"] for account in ACCOUNTS))
    for segment in segments:
        for product in PRODUCTS:
            price = recommended_price(product, segment)
            cost = supplier_cost(product)
            rows.append(
                {
                    "segment": segment,
                    "sku": product["sku"],
                    "recommended_price": price,
                    "supplier_cost": cost,
                    "gross_margin_pct": gross_margin_pct(price, cost),
                    "approval_floor_pct": 22.0 if product["category"] in {"equipment", "imaging", "sterilization"} else 15.0,
                }
            )
    return rows


def build_legacy_quote_history_rows() -> list[dict[str, Any]]:
    return [
        # --- Original accounts: 2–3 quotes each spanning 2025–2026 ---
        {"legacy_quote_id": "LQ-882015", "account_id": "acct-riverfront",  "quote_date": "2025-08-10", "quote_total": 18700.0, "status": "Won",  "lost_reason": None},
        {"legacy_quote_id": "LQ-884201", "account_id": "acct-riverfront",  "quote_date": "2025-11-18", "quote_total": 28900.0, "status": "Won",  "lost_reason": None},
        {"legacy_quote_id": "LQ-887410", "account_id": "acct-riverfront",  "quote_date": "2026-04-05", "quote_total": 34200.0, "status": "Open", "lost_reason": None},
        {"legacy_quote_id": "LQ-883190", "account_id": "acct-lakeside",    "quote_date": "2025-09-14", "quote_total": 4800.0,  "status": "Lost", "lost_reason": "price"},
        {"legacy_quote_id": "LQ-884912", "account_id": "acct-lakeside",    "quote_date": "2026-01-22", "quote_total": 6240.0,  "status": "Won",  "lost_reason": None},
        {"legacy_quote_id": "LQ-887720", "account_id": "acct-lakeside",    "quote_date": "2026-05-08", "quote_total": 9100.0,  "status": "Open", "lost_reason": None},
        {"legacy_quote_id": "LQ-882740", "account_id": "acct-orchard",     "quote_date": "2025-09-30", "quote_total": 41500.0, "status": "Lost", "lost_reason": "competitor"},
        {"legacy_quote_id": "LQ-885330", "account_id": "acct-orchard",     "quote_date": "2026-02-09", "quote_total": 20100.0, "status": "Open", "lost_reason": None},
        {"legacy_quote_id": "LQ-884055", "account_id": "acct-summit",      "quote_date": "2025-10-22", "quote_total": 22000.0, "status": "Lost", "lost_reason": "timing"},
        {"legacy_quote_id": "LQ-885812", "account_id": "acct-summit",      "quote_date": "2026-03-14", "quote_total": 31200.0, "status": "Won",  "lost_reason": None},
        {"legacy_quote_id": "LQ-888001", "account_id": "acct-summit",      "quote_date": "2026-06-01", "quote_total": 47800.0, "status": "Open", "lost_reason": None},
        {"legacy_quote_id": "LQ-885090", "account_id": "acct-brightsmile", "quote_date": "2025-12-11", "quote_total": 8700.0,  "status": "Lost", "lost_reason": "competitor"},
        {"legacy_quote_id": "LQ-886090", "account_id": "acct-brightsmile", "quote_date": "2026-02-28", "quote_total": 14150.0, "status": "Open", "lost_reason": None},
        {"legacy_quote_id": "LQ-884800", "account_id": "acct-meridian",    "quote_date": "2025-11-05", "quote_total": 68000.0, "status": "Won",  "lost_reason": None},
        {"legacy_quote_id": "LQ-886377", "account_id": "acct-meridian",    "quote_date": "2026-04-02", "quote_total": 52400.0, "status": "Won",  "lost_reason": None},
        {"legacy_quote_id": "LQ-888220", "account_id": "acct-meridian",    "quote_date": "2026-06-15", "quote_total": 91000.0, "status": "Open", "lost_reason": None},
        # --- New accounts: 1 quote each ---
        {"legacy_quote_id": "LQ-886500", "account_id": "acct-cascade",    "quote_date": "2026-03-01", "quote_total": 12400.0, "status": "Lost", "lost_reason": "price"},
        {"legacy_quote_id": "LQ-886610", "account_id": "acct-apex",       "quote_date": "2026-04-18", "quote_total": 22800.0, "status": "Won",  "lost_reason": None},
        {"legacy_quote_id": "LQ-886720", "account_id": "acct-sunrise",    "quote_date": "2026-05-02", "quote_total": 9600.0,  "status": "Open", "lost_reason": None},
        {"legacy_quote_id": "LQ-886835", "account_id": "acct-pacific",    "quote_date": "2026-05-20", "quote_total": 145000.0,"status": "Won",  "lost_reason": None},
        {"legacy_quote_id": "LQ-886940", "account_id": "acct-heartland",  "quote_date": "2026-06-06", "quote_total": 31500.0, "status": "Open", "lost_reason": None},
        {"legacy_quote_id": "LQ-887050", "account_id": "acct-coastal",    "quote_date": "2026-03-25", "quote_total": 18700.0, "status": "Lost", "lost_reason": "timing"},
        {"legacy_quote_id": "LQ-887160", "account_id": "acct-northstar",  "quote_date": "2026-05-14", "quote_total": 7200.0,  "status": "Open", "lost_reason": None},
        {"legacy_quote_id": "LQ-887270", "account_id": "acct-grandvalley","quote_date": "2026-04-28", "quote_total": 54600.0, "status": "Won",  "lost_reason": None},
    ]


def build_quote_conversion_history_rows() -> list[dict[str, Any]]:
    return [
        # dimension="segment" rows (original three, now tagged)
        {"dimension": "segment", "value": "growth",     "quote_count": 240, "won_count": 82,  "conversion_pct": 34.2},
        {"dimension": "segment", "value": "mid-market", "quote_count": 410, "won_count": 132, "conversion_pct": 32.2},
        {"dimension": "segment", "value": "enterprise", "quote_count": 175, "won_count": 49,  "conversion_pct": 28.0},
        # dimension="specialty" rows (new)
        {"dimension": "specialty", "value": "general dentistry", "quote_count": 310, "won_count": 105, "conversion_pct": 33.9},
        {"dimension": "specialty", "value": "pediatric",         "quote_count": 88,  "won_count": 34,  "conversion_pct": 38.6},
        {"dimension": "specialty", "value": "oral surgery",      "quote_count": 72,  "won_count": 18,  "conversion_pct": 25.0},
        {"dimension": "specialty", "value": "endodontics",       "quote_count": 64,  "won_count": 22,  "conversion_pct": 34.4},
        {"dimension": "specialty", "value": "orthodontics",      "quote_count": 91,  "won_count": 27,  "conversion_pct": 29.7},
    ]


def build_approval_rule_rows() -> list[dict[str, Any]]:
    return [
        {"rule_id": "margin-floor-equipment", "category": "equipment", "threshold_type": "gross_margin_pct", "threshold_value": 22.0, "approver_role": "Equipment Director"},
        {"rule_id": "margin-floor-imaging", "category": "imaging", "threshold_type": "gross_margin_pct", "threshold_value": 24.0, "approver_role": "Imaging Director"},
        {"rule_id": "large-quote", "category": "all", "threshold_type": "quote_total", "threshold_value": 80000.0, "approver_role": "Regional VP"},
    ]


def build_warranty_eligibility_rows() -> list[dict[str, Any]]:
    """One row per product: which Equipment Care code/plan/rate it carries, if any.

    This seeds the `warranty_eligibility` reference table (synced to Lakebase) and
    is also the app's in-memory fallback. Each eligible product maps to its
    family-specific code and rate; non-eligible products get no plan.
    """
    rows: list[dict[str, Any]] = []
    for product in PRODUCTS:
        plan = WARRANTY_PLANS.get(product["category"])
        # A plan SKU itself is never eligible for a plan of its own.
        eligible = plan is not None and product["sku"] not in WARRANTY_SKUS
        rows.append(
            {
                "sku": product["sku"],
                "eligible": eligible,
                "warranty_sku": plan["warranty_sku"] if eligible else None,
                "warranty_title": plan["warranty_title"] if eligible else None,
                "care_plan_pct": plan["care_plan_pct"] if eligible else 0.0,
                "attach_prompt": "Equipment Care eligible" if eligible else "No warranty prompt",
            }
        )
    return rows


def environment_resource_name(prefix: str, kind: str, environment: str) -> str:
    return f"{prefix}-{kind}-{environment}"


def genie_space_title(prefix: str, environment: str) -> str:
    return environment_resource_name(prefix, "genie", environment)


def build_genie_serialized_space(catalog: str, schema: str, guidance_volume: str) -> str:
    qualified = lambda table: f"{catalog}.{schema}.{table}"
    sample_questions = [
        {"id": "0f1a2b3c4d5e6f708192a3b4c5d6e7f0", "question": ["Build an operatory expansion bundle under $80k and flag approvals."]},
        {
            "id": "1a2b3c4d5e6f708192a3b4c5d6e7f001",
            "question": ["What imaging options fit a practice that already uses cloud practice management software and qualifies for Equipment Care?"],
        },
        {
            "id": "2b3c4d5e6f708192a3b4c5d6e7f00112",
            "question": ["Which quote lines need next-level approval for Riverfront Dental?"],
        },
    ]
    tables = [
        {
            "identifier": qualified("accounts"),
            "description": ["Account master with seller-facing name, segment, specialty, growth stage, chair count, and number of locations. account_record_type distinguishes synthetic_demo_account fixtures from public_demo_prospect research records. Public demo prospects have official-website provenance but do not assert a customer relationship, installed base, spend, or order history. Join on account_id when tailoring products, promotions, order history, installed base, or approval guidance."],
        },
        {
            "identifier": qualified("products"),
            "description": ["Product master with category, pricing tags, and seller-guidance source references."],
        },
        {"identifier": qualified("pricebook"), "description": ["Authoritative demo pricebook for seller quoting."]},
        {"identifier": qualified("bundle_components"), "description": ["Named bundle definitions used by the seller copilot."]},
        {"identifier": qualified("account_history"), "description": ["Order history per account and SKU with reorder_cycle_days (NULL for one-time capital items). Multiple rows per (account, sku) provide order-trend depth. Use DATEDIFF(CURRENT_DATE, last_order_date) > reorder_cycle_days to find overdue consumable reorders."]},
        {"identifier": qualified("installed_base"), "description": ["Installed products by account with install_year and warranty_expires (NULL for software/consumables). Use to identify aging equipment (install_year < 2022) or warranties expiring within 90 days."]},
        {"identifier": qualified("inventory"), "description": ["Availability and lead-time by SKU. High-demand imaging items (CBCT, Scanner) may show qty < 3 with longer lead times."]},
        {"identifier": qualified("promotions"), "description": ["Current promotions with discount_pct and applies_to field ('multi-location DSO', 'pediatric dentistry', 'renewal', 'all'). Join to accounts on specialty or num_locations to find applicable promotions."]},
        {"identifier": qualified("source_freshness"), "description": ["Seller-visible readiness of each upstream source with source, status, and detail fields. Use this table whenever the seller asks whether account, product, order, quote, or document data is current or ready."]},
        {"identifier": qualified("equipment_order_history"), "description": ["OMS order and installation ledger; quantity is units sold per order. SUM(quantity) GROUP BY sku gives total sales volume by SKU."]},
        {"identifier": qualified("supplier_segment_pricing"), "description": ["Segment-based recommended prices, supplier cost, and margin controls."]},
        {"identifier": qualified("supplier_price_book"), "description": ["Legacy CPQ single wholesale cost vs. negotiated supplier cost per SKU; overpay_per_unit is the prevented manufacturer overpayment."]},
        {"identifier": qualified("legacy_quote_history"), "description": ["Legacy CPQ quote history with status (Won/Open/Lost) and lost_reason (price/timing/competitor/null). Multiple quotes per account span 2025–2026."]},
        {"identifier": qualified("quote_conversion_history"), "description": ["Quote conversion benchmarks. dimension column is 'segment' (growth/mid-market/enterprise) or 'specialty' (general dentistry/pediatric/oral surgery/endodontics/orthodontics). Filter by dimension to compare across breakdowns."]},
        {"identifier": qualified("approval_rules"), "description": ["Margin and quote-size rules that determine approval routing."]},
        {"identifier": qualified("warranty_eligibility"), "description": ["Equipment Care coverage by product SKU. Columns: sku (the covered product), eligible (bool), warranty_sku (the SPECIFIC Equipment Care code for that product, e.g. SUPPORT-CARE-IMG for imaging, SUPPORT-CARE-12 for operatory, SUPPORT-CARE-STER for sterilization), warranty_title (plan name), care_plan_pct (annual care price as a fraction of the covered item's value), attach_prompt. Look up warranty_sku and care_plan_pct here to attach the correct Equipment Care plan and price it; never assume a single universal code or a flat fee."]},
    ]
    example_question_sqls = [
        {
            "id": "3c4d5e6f708192a3b4c5d6e7f0011223",
            "question": ["Show the highest priced items tagged for operatory expansion."],
            "sql": [
                f"SELECT sku, title, unit_price FROM {qualified('products')} WHERE bundle_tags_text LIKE '%operatory%' ORDER BY unit_price DESC LIMIT 5"
            ],
        },
        {
            "id": "2b3c4d5e6f708192a3b4c5d6e7001122",
            "question": ["Which Equipment Care code and rate apply to a CBCT imaging unit?"],
            "sql": [
                f"SELECT w.sku, w.warranty_sku, w.warranty_title, w.care_plan_pct FROM {qualified('warranty_eligibility')} w WHERE w.sku = 'IMAG-CBCT-210' AND w.eligible = true"
            ],
        },
        {
            "id": "4d5e6f708192a3b4c5d6e7f001122334",
            "question": ["Show recommended pricing and margin for Riverfront imaging items."],
            "sql": [
                f"SELECT sku, recommended_price, supplier_cost, gross_margin_pct FROM {qualified('supplier_segment_pricing')} WHERE segment = 'mid-market' AND sku IN ('IMAG-CBCT-210', 'SCANNER-CHAIR-01') ORDER BY gross_margin_pct DESC"
            ],
        },
        {
            "id": "5e6f708192a3b4c5d6e7f00112233445",
            "question": ["Which SKU has the highest sales volume?"],
            "sql": [
                f"SELECT sku, SUM(quantity) AS total_quantity FROM {qualified('equipment_order_history')} GROUP BY sku ORDER BY total_quantity DESC LIMIT 10"
            ],
        },
        {
            "id": "6f708192a3b4c5d6e7f001122334455a",
            "question": ["Which accounts are overdue for a consumables reorder?"],
            "sql": [
                f"SELECT account_id, sku, last_order_date, reorder_cycle_days, DATEDIFF(CURRENT_DATE, last_order_date) AS days_since_order FROM {qualified('account_history')} WHERE reorder_cycle_days IS NOT NULL AND DATEDIFF(CURRENT_DATE, last_order_date) > reorder_cycle_days ORDER BY days_since_order DESC"
            ],
        },
        {
            "id": "7080192a3b4c5d6e7f0011223344556b",
            "question": ["Which accounts have equipment warranties expiring in the next 90 days?"],
            "sql": [
                f"SELECT account_id, sku, warranty_expires, DATEDIFF(warranty_expires, CURRENT_DATE) AS days_until_expiry FROM {qualified('installed_base')} WHERE warranty_expires IS NOT NULL AND DATEDIFF(warranty_expires, CURRENT_DATE) BETWEEN 0 AND 90 ORDER BY days_until_expiry ASC"
            ],
        },
        {
            "id": "8091a2b3c4d5e6f7001122334455667c",
            "question": ["What quotes did we lose and why?"],
            "sql": [
                f"SELECT account_id, legacy_quote_id, quote_date, quote_total, lost_reason FROM {qualified('legacy_quote_history')} WHERE status = 'Lost' ORDER BY quote_date DESC"
            ],
        },
    ]
    benchmark_questions = [
        {
            "id": "5e6f708192a3b4c5d6e7f00112233445",
            "question": ["Which Equipment Care plan and rate apply to each imaging item?"],
            "answer": [
                {
                    "format": "SQL",
                    "content": [
                        f"SELECT p.sku, p.title, w.warranty_sku, w.warranty_title, w.care_plan_pct FROM {qualified('products')} p JOIN {qualified('warranty_eligibility')} w ON p.sku = w.sku WHERE p.category = 'imaging' AND w.eligible = true"
                    ],
                }
            ],
        }
    ]
    payload = {
        "version": 2,
        "config": {
            "sample_questions": sorted(sample_questions, key=lambda item: item["id"])
        },
        "data_sources": {
            "tables": sorted(tables, key=lambda table: table["identifier"]),
            "volumes": [
                {"path": f"/Volumes/{catalog}/{schema}/{guidance_volume}/"}
            ],
        },
        "instructions": {
            "text_instructions": [
                {
                    "id": "6f708192a3b4c5d6e7f0011223344556",
                    "content": [
                        "You support field sellers using a modern CPQ workflow. Favor concise answers about segment pricing, supplier cost checks, margin controls, Equipment Care, tiered approvals, customer-ready PDF generation, revision control, follow-up, and source freshness. Treat account_record_type = public_demo_prospect as public research only: state that it is a demo prospect, cite provenance_url when relevant, and never imply a customer relationship or invent commercial history."
                    ],
                }
            ],
            "example_question_sqls": sorted(example_question_sqls, key=lambda item: item["id"]),
        },
        "benchmarks": {
            "questions": sorted(benchmark_questions, key=lambda item: item["id"])
        },
    }
    return json.dumps(payload, separators=(",", ":"))
