import streamlit as st
import pdfplumber
import re
import pandas as pd

def merge_header_tokens(tokens):
    merged = []
    i = 0
    while i < len(tokens):
        if i+2 < len(tokens) and tokens[i] == "PACK" and tokens[i+1] == "LIST" and tokens[i+2] == "ID":
            merged.append("PACK LIST ID")
            i += 3
        elif i+1 < len(tokens) and tokens[i] == "PART" and tokens[i+1] == "ID":
            merged.append("PART ID")
            i += 2
        else:
            merged.append(tokens[i])
            i += 1
    return merged

def merge_numeric_tokens(tokens):
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
    lines = text.splitlines()
    header_index = None
    for i, line in enumerate(lines):
        if "PART ID" in line and "DESCRIPTION" in line:
            header_index = i
            break
    if header_index is None:
        return []
    
    rows = []
    i = header_index + 1
    while i < len(lines):
        if "Country MFG:" in lines[i]:
            break
        if not lines[i].strip():
            i += 1
            continue
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
        part_token = tokens[1]
        part_id = re.sub(r'^\d+\.\d+', '', part_token)
        desc_tokens = []
        for token in tokens[2:]:
            if token.startswith('$'):
                break
            desc_tokens.append(token)
        description = " ".join(desc_tokens)
        parts.append((part_id, description))
    return parts

def get_pack_list_id_from_tokens(text_lines):
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

def extract_invoice_data(pdf_file):
    invoice_data = {
        'Invoice ID': None,
        'PACK LIST ID': None,
        'Harmonization Code': None,
        'PARTS': []  # List of tuples: (PART ID, DESCRIPTION)
    }
    
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            if invoice_data['Invoice ID'] is None:
                match = re.search(r'Invoice ID:\s*(\S+)', text)
                if match:
                    invoice_data['Invoice ID'] = match.group(1)
            if invoice_data['Harmonization Code'] is None:
                match = re.search(r'Harmonization Code:\s*([\d\.]+)', text)
                if match:
                    invoice_data['Harmonization Code'] = match.group(1)
            
            lines = text.splitlines()
            pack_list_id = get_pack_list_id_from_tokens(lines)
            if pack_list_id and invoice_data['PACK LIST ID'] is None:
                invoice_data['PACK LIST ID'] = pack_list_id

            parts = get_all_parts(text)
            if parts:
                invoice_data['PARTS'].extend(parts)
            
            if (invoice_data['Invoice ID'] and invoice_data['Harmonization Code'] and
                invoice_data['PACK LIST ID'] and invoice_data['PARTS']):
                break
    return invoice_data

# Streamlit UI
st.title("Novanta PDF Reader")
st.write("Upload one or more PDFs")

uploaded_files = st.file_uploader("Choose PDF files", type="pdf", accept_multiple_files=True)

if uploaded_files:
    # We'll create a list to store rows of data.
    all_rows = []
    
    for uploaded_file in uploaded_files:
        try:
            inv_data = extract_invoice_data(uploaded_file)
            # Flatten the data: one row per part, duplicating invoice-level info.
            for part in inv_data["PARTS"]:
                row = {
                    "Invoice ID": inv_data["Invoice ID"],
                    "PACK LIST ID": inv_data["PACK LIST ID"],
                    "Harmonization Code": inv_data["Harmonization Code"],
                    "PART ID": part[0],
                    "DESCRIPTION": part[1]
                }
                all_rows.append(row)
        except Exception as e:
            st.error(f"Error processing file {uploaded_file.name}: {e}")
    
    if all_rows:
        df = pd.DataFrame(all_rows)
        st.markdown("### Combined Invoice Data")
        st.dataframe(df)
    else:
        st.write("No data extracted from the uploaded PDFs.")
