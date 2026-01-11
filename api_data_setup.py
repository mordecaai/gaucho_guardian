import requests
import json

MY_API_KEY = input("Enter API key: ")

headers = {
    'accept': 'text/plain',
    'ucsb-api-key': MY_API_KEY
}

# checks if the class code is valid
def fetch_class_data(class_code):
    date = "20261"
    url = f"https://api.ucsb.edu/academics/curriculums/v3/classes/{date}/{class_code}?includeClassSections=true"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        return None

#confirm check, test for ece 5


# enter searching parameters
basic_search_parameters = {
  # For a general search filtering by area or college, use parameters like college and subjectArea
  "college": "Engineering",          # Example: "Engineering", "Letters and Science", etc.
  "subjectArea": "ANTH",            # Example: "CMPSC", "ECE", "MATH", etc.
}

dept_codes = [
    ["ANTH", ["00018", "00232", "00398", "00406", "00414", "00422", "54049", "00737", "00786", "54247"]],
    ["ENGL", ["17947", "17954", "51516", "17962", "59667", "17988", "51573", "18051", "18168", "55673"]],
    ["ENV", ["18978", "19307", "19372"]]
  ]
# loop and look for correct subject areas

class_info_list = []

for dept in dept_codes:
    print("gets here")
    dept_title = dept[0]
    if dept_title in basic_search_parameters["subjectArea"].split(","):
        print(f"Department '{dept_title}' found in search parameters.")
        print(f"List of codes for {dept_title}:")
        for code in dept[1]:
            class_info = fetch_class_data(code)
            class_info_list.append([dept_title, code, class_info])
            print(code, " " , class_info.get("title"))
        break
