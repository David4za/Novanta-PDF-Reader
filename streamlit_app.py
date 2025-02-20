import streamlit as st
import pdfplumber
import re
import pandas as pd

def merge_header_tokens(tokens):
    """
    Merge multi-word header tokens.
    Now also merges "SHIPPING METHOD" and "SHIP DATE".
    """
    merged = []
    i = 0
    while i < len(tokens):
        if i+2 < len(tokens) and tokens[i] == "PACK" and tokens[i+1] == "LIST" and tokens[i+2] == "ID":
            merged.append("PACK LIST ID")
            i += 3
        elif i+1 < len(tokens) and tokens[i] == "PART" and tokens[i+1] == "ID":
            merged.append("PART ID")
            i += 2
        elif i+1 < len(tokens) and tokens[i] == "SHIPPING" and tokens[i+1] == "METHOD":
            merged.append("SHIPPING METHOD")
            i += 2
        elif i+1 < len(tokens) and tokens[i] == "SHIP" and tokens[i+1] == "DATE":
            merged.append("SHIP DATE")
            i += 2
        else:
            merged.append(tokens[i])
            i += 1
    return merged

def merge_numeric_tokens(tokens):
    """
    Merge tokens that appear to be split parts of a number.
    For example, merge ['25.0', '0'] into ['25.00'].
    """
    merged = []
    skip_next = False
    for i in range(len(tokens)):
        if skip_next:
            skip_next = False
            continue
        if i < len(tokens) - 1 and re.match(r'^\d+\.\d*$', tokens[i]) and re.match(r'^\d+$', tokens[i+1]):
            merged.append(tokens[i] + tokens[i+1])
            skip_next = True
        else:
            merged.append(tokens[i])
    return merged

def get_all_parts(text):
    """
    Extract parts from the parts table.
    Returns a list of tuples: (PART ID, DESCRIPTION, Unit Price, Extended Price)
    """
    lines = text.splitlines()
    header_index = None
    for i, line in enumerate(lines):
        if "PART ID" in line and "DESCRIPTION" in line:
            header_index = i
            break
    if header_index is None:
        return []
    
    # Collect rows until "Country MFG:" is encountered
    rows = []
    i = header_index + 1
    while i < len(lines):
        if "Country MFG:" in lines[i]:
            break
        if not lines[i].strip():
            i += 1
            continue
        # If the line is purely numeric (e.g., "00003"), append it to the previous row
        if re.match(r'^\d+$', lines[i].strip()):
            if rows:
                rows[-1] = rows[-1] + " " + lines[i].strip()
            i += 1
            continue
        rows.append(lines[i].strip())
        i += 1

    parts = []
    for row in rows:
        tokens = row.split()
        if len(tokens) < 3:
            continue
        # token[1] holds the shipped amount and PART ID combined;
        # strip the numeric part to get the actual PART ID.
        part_token = tokens[1]
        part_id = re.sub(r'^\d+\.\d+', '', part_token)
        
        # Extract the description tokens until we hit the first token starting with '$'
        # Then capture the next two price tokens as Unit Price and Extended Price.
        desc_tokens = []
        price_tokens = []
        for token in tokens[2:]:
            if token.startswith('$'):
                price_tokens.append(token)
            else:
                if not price_tokens:
                    desc_tokens.append(token)
                else:
                    price_tokens.append(token)
        description = " ".join(desc_tokens)
        unit_price = price_tokens[0] if len(price_tokens) >= 1 else None
        extended_price = price_tokens[1] if len(price_tokens) >= 2 else None
        parts.append((part_id, description, unit_price, extended_price))
    return parts

def get_pack_list_id_from_tokens(text_lines):
    """
    Extract PACK LIST ID from the header and its following data row.
    """
    for i, line in enumerate(text_lines):
        if "PACK" in line and "LIST" in line and "ID" in line:
            header_line = line
            data_line = text_lines[i+1] if i+1 < len(text_lines) else ""
            header_tokens = merge_header_tokens(header_line.split())
            raw_data_tokens = data_line.split()
            fixed_data_tokens = []
            for token in raw_data_tokens:
                match = re.match(r'^(\d+\.\d+)([A-Za-z0-9\-]+)$', token)
                if match:
                    fixed_data_tokens.extend([match.group(1), match.group(2)])
                else:
                    fixed_data_tokens.append(token)
            data_tokens = merge_numeric_tokens(fixed_data_tokens)
            if "PACK LIST ID" in header_tokens:
                idx = header_tokens.index("PACK LIST ID")
                if idx < len(data_tokens):
                    return data_tokens[idx]
    return None

def get_shipping_info(text_lines):
    """
    Extract Shipping Method and Ship Date from the shipping info block.
    Expects the header line like:
    "PACK LIST ID SALES REP ID SHIPPING METHOD SHIP DATE INVOICE DUE DATE"
    and a data row such as:
    "182371 INTL UPS WORLDWIDE EXPEDITED COLLECT BLUE 03/28/2024 04/27/2024"
    """
    shipping_method = None
    ship_date = None
    for i, line in enumerate(text_lines):
        if "SHIPPING METHOD" in line and "SHIP DATE" in line:
            if i+1 < len(text_lines):
                data_line = text_lines[i+1]
                data_tokens = data_line.split()
                # Assuming:
                # data_tokens[0] = PACK LIST ID
                # data_tokens[1] = SALES REP ID
                # data_tokens[2:-2] = SHIPPING METHOD (could be multiple tokens)
                # data_tokens[-2] = SHIP DATE
                # data_tokens[-1] = INVOICE DUE DATE
                if len(data_tokens) >= 5:
                    shipping_method = " ".join(data_tokens[2:-2])
                    ship_date = data_tokens[-2]
            break
    return shipping_method, ship_date


def get_ship_to_address(text):
    """
    Extract the Ship To Address from the block following the header:
    "Bill To Address Ship To Address"
    Uses a heuristic to split each line into two halves and take the right (ship-to) side.
    Stops reading once a line equals "NL".
    """
    lines = text.splitlines()
    start_index = None
    for i, line in enumerate(lines):
        if "Bill To Address" in line and "Ship To Address" in line:
            start_index = i
            break
    if start_index is None:
        return None
    addr_lines = []
    for line in lines[start_index+1:]:
        if line.strip() == "" or line.strip() == "NL":
            break
        tokens = line.split()
        n = len(tokens)
        if n % 2 == 0:
            first_half = " ".join(tokens[:n//2])
            second_half = " ".join(tokens[n//2:])
            # If both halves are the same, we just take one; otherwise, assume ship-to is the second half.
            addr_lines.append(second_half)
        else:
            addr_lines.append(line)
    return "\n".join(addr_lines)

def extract_invoice_data(pdf_file):
    """
    Extract various fields from the PDF.
    Returns a dictionary with keys:
      - Invoice ID
      - PACK LIST ID
      - Harmonization Code
      - Customer PO (starts with 450)
      - Shipping Method
      - Ship Date
      - Ship To Address
      - PARTS: list of tuples (PART ID, DESCRIPTION, Unit Price, Extended Price)
    """
    invoice_data = {
        'Invoice ID': None,
        'PACK LIST ID': None,
        'Harmonization Code': None,
        'Customer PO': None,
        'Shipping Method': None,
        'Ship Date': None,
        'Ship To Address': None,
        'PARTS': []  # List of tuples: (PART ID, DESCRIPTION, Unit Price, Extended Price)
    }
    
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            
            # Invoice ID
            if invoice_data['Invoice ID'] is None:
                match = re.search(r'Invoice ID:\s*(\S+)', text)
                if match:
                    invoice_data['Invoice ID'] = match.group(1)
            
            # Harmonization Code
            if invoice_data['Harmonization Code'] is None:
                match = re.search(r'Harmonization Code:\s*([\d\.]+)', text)
                if match:
                    invoice_data['Harmonization Code'] = match.group(1)
            
            # Customer PO (starts with 450)
            if invoice_data['Customer PO'] is None:
                match = re.search(r'\b(450\d+)\b', text)
                if match:
                    invoice_data['Customer PO'] = match.group(1)
            
            lines = text.splitlines()
            
            # PACK LIST ID
            pack_list_id = get_pack_list_id_from_tokens(lines)
            if pack_list_id and invoice_data['PACK LIST ID'] is None:
                invoice_data['PACK LIST ID'] = pack_list_id

            # Parts table (including Unit Price and Extended Price)
            parts = get_all_parts(text)
            if parts:
                invoice_data['PARTS'].extend(parts)
            
            # Shipping info: Shipping Method and Ship Date
            shipping_method, ship_date = get_shipping_info(lines)
            if shipping_method and invoice_data['Shipping Method'] is None:
                invoice_data['Shipping Method'] = shipping_method
            if ship_date and invoice_data['Ship Date'] is None:
                invoice_data['Ship Date'] = ship_date
            
            # Ship To Address
            if invoice_data['Ship To Address'] is None:
                ship_to = get_ship_to_address(text)
                if ship_to:
                    invoice_data['Ship To Address'] = ship_to
            
            # Optionally break early if all fields are found
            if (invoice_data['Invoice ID'] and invoice_data['Harmonization Code'] and
                invoice_data['PACK LIST ID'] and invoice_data['Customer PO'] and
                invoice_data['Shipping Method'] and invoice_data['Ship Date'] and
                invoice_data['Ship To Address'] and invoice_data['PARTS']):
                break
    
    return invoice_data
    
# Streamlit
st.title("Novanta PDF Reader")
st.write("Upload one or more PDFs")
uploaded_files = st.file_uploader("Choose PDF files", type="pdf", accept_multiple_files=True)
# After processing each uploaded PDF:
if uploaded_files:
    all_rows = []
    for uploaded_file in uploaded_files:
        try:
            inv_data = extract_invoice_data(uploaded_file)
            filename = uploaded_file.name  # get filename from uploader
            
            # For each part, create a row that includes all invoice-level and part-level details.
            for part in inv_data["PARTS"]:
                row = {
                    "Filename": [:rainbow[filename]],
                    "Invoice ID": inv_data["Invoice ID"],
                    "PACK LIST ID": inv_data["PACK LIST ID"],
                    "Harmonization Code": inv_data["Harmonization Code"],
                    "Customer PO": inv_data["Customer PO"],
                    "PART ID": part[0],
                    "Description": part[1],
                    "Unit Price": part[2],
                    "Extended Price": part[3],
                    "Shipping Method": inv_data["Shipping Method"],
                    "Ship Date": inv_data["Ship Date"],
                    "Ship To Address": inv_data["Ship To Address"]
                }
                all_rows.append(row)
        except Exception as e:
            st.error(f"Error processing file {uploaded_file.name}: {e}")
    
    if all_rows:
        df = pd.DataFrame(all_rows)
        st.markdown("### Combined Invoice Data")
        st.write("Columns present:", df.columns.tolist())
        st.dataframe(df, use_container_width=True)
    else:
        st.write("No data extracted from the uploaded PDFs.")
