import requests
import json

MY_API_KEY = input("Enter your API key: ")

headers = {
    'accept': 'text/plain',
    'ucsb-api-key': MY_API_KEY
}
date = "20261"
class_code = "11593"
url = f"https://api.ucsb.edu/academics/curriculums/v3/classes/{date}/{class_code}?includeClassSections=true"


def isValidCode(year, quarter, class_code):
  response = requests.get(url, headers=headers)
  # Checking for sucessful request
  if response.status_code == 200:
      data = response.json()
      if(data): #check if data exists for pulling correct codes
        print(data.get("title")) 
        return True
        
      else:
        return False

#confirm check, test for ece 5
print(isValidCode(2026,1,11593))
