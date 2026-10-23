# engine/schemas.py

CUSTOMER_SCHEMA_V19 = {
    "Name": {"required": True, "default": None, "dtype": "str"},
    "Job Position": {"required": False, "default": None, "dtype": "str"},
    "Mobile": {"required": False, "default": None, "dtype": "str"},
    "Phone": {"required": False, "default": None, "dtype": "str"},
    "Email": {"required": False, "default": None, "dtype": "str"},
    "Street": {"required": False, "default": None, "dtype": "str"},
    "Street2": {"required": False, "default": None, "dtype": "str"},
    "City": {"required": False, "default": None, "dtype": "str"},
    "State": {"required": False, "default": None, "dtype": "str"},
    "Zip": {"required": False, "default": None, "dtype": "str"},
    "Country": {"required": False, "default": None, "dtype": "str"},
    "Website": {"required": False, "default": None, "dtype": "str"},
    "Is a Company": {"required": False, "default": False, "dtype": "bool"},
    "Reference": {"required": False, "default": None, "dtype": "str"},
    "Credit Limit": {"required": False, "default": 0, "dtype": "float"},
    "Branch": {"required": False, "default": None, "dtype": "str"},
    "Customer Rank": {"required": False, "default": 1, "dtype": "int"},
    "Salesperson": {"required": False, "default": None, "dtype": "str"},
    "Category": {"required": False, "default": None, "dtype": "str"},
    "Sub Category": {"required": False, "default": None, "dtype": "str"},
    "Note": {"required": False, "default": None, "dtype": "str"},
    "Account Receivable": {"required": False, "default": None, "dtype": "str"},
    "Account Payable": {"required": False, "default": None, "dtype": "str"},
    "contacts / name": {"required": False, "default": None, "dtype": "str"},
    "contacts / email": {"required": False, "default": None, "dtype": "str"},
    "contacts / title": {"required": False, "default": None, "dtype": "str"},
    "contacts / phone": {"required": False, "default": None, "dtype": "str"},
    "contacts / mobile": {"required": False, "default": None, "dtype": "str"},
    "contacts / Job Title": {"required": False, "default": None, "dtype": "str"},
}

CUSTOMER_SCHEMA_V20 = {
    "Name": {"required": True, "default": None, "dtype": "str"},
    "Email": {"required": True, "default": None, "dtype": "str"},
    "Phone": {"required": True, "default": None, "dtype": "str"},
    "Job Position": {"required": False, "default": None, "dtype": "str"},
    "Website": {"required": False, "default": None, "dtype": "str"},
    "Street": {"required": False, "default": None, "dtype": "str"},
    "City": {"required": False, "default": None, "dtype": "str"},
    "Country": {"required": False, "default": None, "dtype": "str"},
    "Related Contacts/Name": {"required": False, "default": None, "dtype": "str"},
    "Related Contacts/Phone": {"required": False, "default": None, "dtype": "str"},
    "Related Contacts/Job Position": {
        "required": False,
        "default": None,
        "dtype": "str",
    },
}

VENDOR_SCHEMA_V19 = {
    "Vendor Name": {"required": True, "default": None, "dtype": "str"},
    "Street": {"required": False, "default": None, "dtype": "str"},
    "Street2": {"required": False, "default": None, "dtype": "str"},
    "City": {"required": False, "default": None, "dtype": "str"},
    "State": {"required": False, "default": None, "dtype": "str"},
    "Zip": {"required": False, "default": None, "dtype": "str"},
    "Country": {"required": False, "default": None, "dtype": "str"},
    "Tax ID": {"required": False, "default": None, "dtype": "str"},
    "Phone": {"required": False, "default": None, "dtype": "str"},
    "Mobile": {"required": False, "default": None, "dtype": "str"},
    "Email": {"required": False, "default": None, "dtype": "str"},
    "Website": {"required": False, "default": None, "dtype": "str"},
    "Reference": {"required": False, "default": None, "dtype": "str"},
    "Supplier Rank": {"required": False, "default": 1, "dtype": "int"},
    "Address Type": {"required": False, "default": None, "dtype": "str"},
    "Tags": {"required": False, "default": None, "dtype": "str"},
    "Contact/Name": {"required": False, "default": None, "dtype": "str"},
    "Contact/Title": {"required": False, "default": None, "dtype": "str"},
    "Contact/Job Position": {"required": False, "default": None, "dtype": "str"},
    "Contact/Email": {"required": False, "default": None, "dtype": "str"},
    "Contact/Phone": {"required": False, "default": None, "dtype": "str"},
    "Contact/Mobile": {"required": False, "default": None, "dtype": "str"},
}

VENDOR_SCHEMA_V20 = {
    "Name": {"required": True, "default": None, "dtype": "str"},
    "Email": {"required": True, "default": None, "dtype": "str"},
    "Phone": {"required": True, "default": None, "dtype": "str"},
    "Job Position": {"required": False, "default": None, "dtype": "str"},
    "Country": {"required": False, "default": None, "dtype": "str"},
    "City": {"required": False, "default": None, "dtype": "str"},
    "State": {"required": False, "default": None, "dtype": "str"},
    "Website": {"required": False, "default": None, "dtype": "str"},
    "Related Contacts/Name": {"required": False, "default": None, "dtype": "str"},
    "Related Contacts/Job": {"required": False, "default": None, "dtype": "str"},
    "Related Contacts/Phone": {"required": False, "default": None, "dtype": "str"},
}

SCHEMA_MAP = {
    "customer": {
        "v19": CUSTOMER_SCHEMA_V19,
        "v20": CUSTOMER_SCHEMA_V20,
    },
    "vendor": {
        "v19": VENDOR_SCHEMA_V19,
        "v20": VENDOR_SCHEMA_V20,
    },
}

MANDATORY_FIELD = {
    "customer": {
        "v19": ["Name"],
        "v20": ["Name", "Email", "Phone"],
    },
    "vendor": {
        "v19": ["Vendor Name"],
        "v20": ["Name", "Email", "Phone"],
    },
}


def get_schema(data_type: str, version: str) -> dict:
    if data_type not in SCHEMA_MAP:
        raise ValueError(f"Unsupported data type: '{data_type}'")

    if version not in SCHEMA_MAP[data_type]:
        raise ValueError(
            f"Odoo version '{version}' is not yet supported for {data_type}s. "
            f"Currently supported: {list(SCHEMA_MAP[data_type].keys())}"
        )

    return SCHEMA_MAP[data_type][version]
