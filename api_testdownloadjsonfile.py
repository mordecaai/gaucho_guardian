import requests
import json

# --- CONFIGURATION ---
MY_API_KEY = input("Enter your API key: ")
DATE = "20261"  # Winter 2026

headers = {
    'accept': 'application/json',
    'ucsb-api-key': MY_API_KEY
}

def download_multiple_classes(class_codes):
    """Loops through a list of codes and downloads each one."""
    
    for code in class_codes:
        # Build the URL dynamically for each code
        url = f"https://api.ucsb.edu/academics/curriculums/v3/classes/{DATE}/{code}?includeClassSections=true"
        
        print(f"📡 Fetching data for {code}...")
        
        try:
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check if the API actually returned a course or just an empty object
                if data and "courseId" in data:
                    filename = f"class_{code}.json"
                    with open(filename, 'w') as f:
                        json.dump(data, f, indent=4)
                    print(f"   ✅ Saved to {filename}")
                else:
                    print(f"   ❌ No course data found for code {code}.")
            else:
                print(f"   ⚠️ Request failed for {code} (Status: {response.status_code})")
        
        except Exception as e:
            print(f"   🚨 An error occurred while downloading {code}: {e}")

# --- EXECUTION ---
# Add all the enroll codes you want to download here:
codes_to_get = ["25007", "11585", "29215"]

download_multiple_classes(codes_to_get)