#!/usr/bin/env python3
"""
Analyze discrepancies between input CSV, expected result, and model outputs.
"""

import csv
from collections import defaultdict

def read_csv(filename):
    """Read CSV and return list of dicts."""
    with open(filename, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        return list(reader)

def parse_date(date_str):
    """Convert date from DD/MM/YYYY to YYYY-MM-DD."""
    if not date_str:
        return None
    date_str = date_str.strip()
    if '-' in date_str and len(date_str) == 10 and date_str[4] == '-':
        # Already in YYYY-MM-DD format
        return date_str
    parts = date_str.split('/')
    if len(parts) == 3:
        day, month, year = parts
        if len(year) == 2:
            year = '20' + year
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    return date_str

def analyze_input(input_file):
    """Analyze input file and return expected output lines."""
    rows = read_csv(input_file)
    
    expected = []
    issues = []
    
    for i, row in enumerate(rows, start=2):  # Row 2 is first data row
        refno = row.get('Candidate RefNo', '').strip()
        client = row.get('Client Name', '').strip()
        job_title = row.get('Contract JobTitle', '').strip()
        forename = row.get('Candidate Forename', '').strip()
        surname = row.get('Candidate Surname', '').strip()
        weekending = row.get('Weekending', '').strip()
        
        # Parse numeric values
        def parse_num(val):
            if not val:
                return 0.0
            val = val.strip().replace(',', '')
            try:
                return float(val)
            except:
                return 0.0
        
        # Get values - handle potential column name variations
        std_hrs = parse_num(row.get('Std1 Hrs') or row.get('Std Hrs') or '0')
        ot1_hrs = parse_num(row.get('OT1 Hrs') or row.get('OT1 HR') or '0')
        std_rate = parse_num(row.get('Std Rate') or row.get('Rate') or '0')
        ot1_rate = parse_num(row.get('OT1 Rate') or '0')
        expenses = parse_num(row.get('Expenses') or '0')
        net_pay = parse_num(row.get('Net Pay') or '0')
        
        if not refno or not forename or not surname or not weekending:
            continue
            
        weekending_formatted = parse_date(weekending)
        
        # Expected lines based on rules
        if expenses > 0:
            expected.append({
                'employeeid': refno,
                'firstname': forename,
                'surname': surname,
                'description': f"Expenses - {client} - {job_title}",
                'amount': 1,
                'rate': expenses,
                'weekending': weekending_formatted,
                'unit': 'expense',
                'input_row': i,
                'type': 'Expenses'
            })
        
        if std_hrs > 0 and std_rate > 0:
            expected.append({
                'employeeid': refno,
                'firstname': forename,
                'surname': surname,
                'description': f"Std Hrs - {client} - {job_title}",
                'amount': std_hrs,
                'rate': std_rate,
                'weekending': weekending_formatted,
                'unit': 'hours',
                'input_row': i,
                'type': 'Std Hrs'
            })
        
        if ot1_hrs > 0 and ot1_rate > 0:
            expected.append({
                'employeeid': refno,
                'firstname': forename,
                'surname': surname,
                'description': f"OT1 Hrs - {client} - {job_title}",
                'amount': ot1_hrs,
                'rate': ot1_rate,
                'weekending': weekending_formatted,
                'unit': 'hours',
                'input_row': i,
                'type': 'OT1 Hrs'
            })
        
        # Check for potential issues
        if ot1_rate > 0 and ot1_hrs == 0:
            issues.append({
                'row': i,
                'refno': refno,
                'name': f"{forename} {surname}",
                'issue': f"OT1 Rate = {ot1_rate} but OT1 Hrs = 0. Model might confuse this."
            })
    
    return expected, issues

def compare_outputs(expected, actual_file, label):
    """Compare expected output with actual output file."""
    actual_rows = read_csv(actual_file)
    
    discrepancies = []
    
    # Group actual by employeeid + weekending + type
    actual_by_key = defaultdict(list)
    for row in actual_rows:
        desc = row.get('description', '')
        line_type = 'Unknown'
        if desc.startswith('Std Hrs'):
            line_type = 'Std Hrs'
        elif desc.startswith('OT1 Hrs'):
            line_type = 'OT1 Hrs'
        elif desc.startswith('OT2 Hrs'):
            line_type = 'OT2 Hrs'
        elif desc.startswith('OT3 Hrs'):
            line_type = 'OT3 Hrs'
        elif desc.startswith('Expenses'):
            line_type = 'Expenses'
        
        key = (row.get('employeeid', '').strip(), row.get('weekending', '').strip(), line_type)
        actual_by_key[key].append(row)
    
    # Check for lines in actual but not expected (or with wrong values)
    for key, actual_lines in actual_by_key.items():
        emp_id, we, line_type = key
        
        # Find matching expected
        matching_expected = [e for e in expected if 
                          e['employeeid'] == emp_id and 
                          e['weekending'] == we and
                          e['type'] == line_type]
        
        if not matching_expected and actual_lines:
            for al in actual_lines:
                discrepancies.append({
                    'type': 'EXTRA_LINE',
                    'employeeid': emp_id,
                    'description': al.get('description', ''),
                    'amount': al.get('amount', ''),
                    'rate': al.get('rate', ''),
                    'weekending': al.get('weekending', ''),
                    'issue': f"Line exists in {label} but shouldn't based on input"
                })
    
    return discrepancies

def main():
    print("=" * 80)
    print("TIMESHEET MODEL VALIDATION ANALYSIS")
    print("=" * 80)
    
    # Analyze input
    input_file = 'FawkesandReece(South).south (input).csv'
    expected, potential_issues = analyze_input(input_file)
    
    print(f"\n### Input Analysis ###")
    print(f"Total rows in input: {len(read_csv(input_file))}")
    print(f"Total expected output lines from input: {len(expected)}")
    
    print(f"\n### Potential Problem Rows (OT Rate without OT Hours) ###")
    for issue in potential_issues:
        print(f"  Row {issue['row']}: {issue['refno']} ({issue['name']})")
        print(f"    - {issue['issue']}")
    
    # Read all output files
    wrong_output = read_csv('Wrong Output.csv')
    expected_result = read_csv('FawkesandReece(South).south result.csv')
    latest_result = read_csv('Latest Result FawkesandReece(South).csv')
    
    print(f"\n### Output File Line Counts ###")
    print(f"  Expected Result:  {len(expected_result)} lines")
    print(f"  Wrong Output:     {len(wrong_output)} lines")
    print(f"  Latest Result:    {len(latest_result)} lines")
    print(f"  Calculated from input: {len(expected)} lines")
    
    # Find specific discrepancies
    print(f"\n### CRITICAL ISSUES IN 'Wrong Output.csv' ###")
    
    # Check each row in wrong output for issues
    input_rows = read_csv(input_file)
    input_by_refno = {}
    for row in input_rows:
        refno = row.get('Candidate RefNo', '').strip()
        we = row.get('Weekending', '').strip()
        key = (refno, parse_date(we))
        if key not in input_by_refno:
            input_by_refno[key] = []
        input_by_refno[key].append(row)
    
    issues_found = []
    
    for row in wrong_output:
        emp_id = row.get('employeeid', '').strip()
        desc = row.get('description', '')
        amount = row.get('amount', '').strip()
        rate = row.get('rate', '').strip()
        we = row.get('weekending', '').strip()
        
        key = (emp_id, we)
        input_data = input_by_refno.get(key, [])
        
        if not input_data:
            continue
        
        for inp in input_data:
            def parse_num(val):
                if not val:
                    return 0.0
                val = val.strip().replace(',', '')
                try:
                    return float(val)
                except:
                    return 0.0
            
            ot1_hrs = parse_num(inp.get('OT1 Hrs', '0'))
            ot1_rate = parse_num(inp.get('OT1 Rate', '0'))
            expenses = parse_num(inp.get('Expenses', '0'))
            
            # Issue: OT1 line when OT1 Hrs = 0
            if 'OT1 Hrs' in desc and ot1_hrs == 0:
                issues_found.append({
                    'employeeid': emp_id,
                    'name': f"{row.get('firstname', '')} {row.get('surname', '')}",
                    'issue': f"OT1 line created but input OT1 Hrs = 0 (OT1 Rate = {ot1_rate})",
                    'output_line': f"{desc}, amount={amount}, rate={rate}",
                    'severity': 'CRITICAL'
                })
            
            # Issue: Expenses line when Expenses = 0
            if 'Expenses' in desc and expenses == 0:
                issues_found.append({
                    'employeeid': emp_id,
                    'name': f"{row.get('firstname', '')} {row.get('surname', '')}",
                    'issue': f"Expenses line created but input Expenses = 0 (OT1 Rate = {ot1_rate} may have been confused)",
                    'output_line': f"{desc}, amount={amount}, rate={rate}",
                    'severity': 'CRITICAL'
                })
            
            # Issue: Amount and Rate swapped (rate looks like hours, amount looks like rate)
            try:
                amt = float(amount)
                rt = float(rate)
                if amt > 100 and rt <= 10 and 'Hrs' in desc:
                    issues_found.append({
                        'employeeid': emp_id,
                        'name': f"{row.get('firstname', '')} {row.get('surname', '')}",
                        'issue': f"Amount ({amt}) and Rate ({rt}) appear to be swapped",
                        'output_line': f"{desc}, amount={amount}, rate={rate}",
                        'severity': 'CRITICAL'
                    })
            except:
                pass
    
    for issue in issues_found:
        print(f"\n  [{issue['severity']}] {issue['employeeid']} ({issue['name']})")
        print(f"    Issue: {issue['issue']}")
        print(f"    Output: {issue['output_line']}")
    
    # Check dates in expected result
    print(f"\n### DATE ISSUES IN 'Expected Result' ###")
    for row in expected_result:
        emp_id = row.get('employeeid', '').strip()
        we = row.get('weekending', '').strip()
        
        # Find in input
        for inp in input_rows:
            if inp.get('Candidate RefNo', '').strip() == emp_id:
                input_we = parse_date(inp.get('Weekending', ''))
                if input_we != we:
                    # Check if the wrong date matches the DOB
                    dob = inp.get('Candidate DOB', '')
                    if dob:
                        dob_parts = dob.split('/')
                        if len(dob_parts) >= 2:
                            potential_wrong = f"2025-{dob_parts[1].zfill(2)}-{dob_parts[0].zfill(2)}"
                            if we == potential_wrong:
                                print(f"  {emp_id}: Date {we} appears to use DOB ({dob}) instead of Weekending ({input_we})")
                break

if __name__ == '__main__':
    main()
