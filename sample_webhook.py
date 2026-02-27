import requests
import os

MAKE_WEBHOOK_URL = "https://hook.eu1.make.com/kh12l3eo71hhyfxjkhu8gkkjmkuvx28j"

data = {
    "campaign_name": "Test Campaign",
    "campaign_purpose": "Test Purpose",
    "tone": "Professional",
    "voice": "female",
    "numbers": ["+911234567890", "+919876543210"]
}

response = requests.post(MAKE_WEBHOOK_URL, json=data)

print("Status Code:", response.status_code)
print("Response:", response.text)