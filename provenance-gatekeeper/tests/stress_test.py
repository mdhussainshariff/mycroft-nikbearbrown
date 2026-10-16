import requests

API_URL = "http://localhost:8000/verify"

# Assuming the seeded ChromaDB ground truth is still:
# "The company revenue grew to exactly 5000000 this quarter."
adversarial_payloads = [
    # These should now PASS (Valid variants of 5,000,000)
    {"claim_id": "NORM-01", "generated_claim": "$5,000,000.00"},       
    {"claim_id": "NORM-02", "generated_claim": "5.0M"},                
    {"claim_id": "NORM-03", "generated_claim": "exactly 5 million"}, 
    {"claim_id": "NORM-04", "generated_claim": "5000000"}, 
    
    # These should FAIL (Magnitude errors)
    {"claim_id": "STRESS-01", "generated_claim": "$4,500,000.00"},       
    {"claim_id": "STRESS-02", "generated_claim": "4.5M"}, 
    
    # These should FAIL (Data type errors / SQL Injection)
    {"claim_id": "STRESS-03", "generated_claim": "N/A"},                    
    {"claim_id": "STRESS-04", "generated_claim": "null"},                     
    {"claim_id": "STRESS-05", "generated_claim": "DROP TABLE logs;"}        
]

print("COMMENCING NORMALIZATION & STRESS TEST...\n")

for i, payload in enumerate(adversarial_payloads):
    try:
        response = requests.post(API_URL, json=payload)
        status = response.status_code
        
        if status == 200:
            result = response.json().get("verdict", "UNKNOWN")
            variance = response.json().get("variance_type", "")
            print(f"Test {i+1:<2} | Claim: {payload['generated_claim']:<20} | Verdict: {result} | Type: {variance}")
        else:
            result = response.json().get("detail", "HTTP ERROR")
            print(f"Test {i+1:<2} | Claim: {payload['generated_claim']:<20} | Status: {status} | Error: {result}")
            
    except Exception as e:
        print(f"Test {i+1:<2} | Claim: {payload['generated_claim']:<20} | FATAL CRASH: {e}")