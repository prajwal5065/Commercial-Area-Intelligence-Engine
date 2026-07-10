import sys, os
sys.path.insert(0, r'c:\Users\admin\Desktop\oxiai\SUB_AREA_MAPPER\SUB AGENT 2')
sys.path.insert(0, r'c:\Users\admin\Desktop\oxiai\SUB_AREA_MAPPER')
from dotenv import load_dotenv
load_dotenv(r'c:\Users\admin\Desktop\oxiai\SUB_AREA_MAPPER\.env')
from config import GEMINI_MODEL
print("GEMINI_MODEL =", GEMINI_MODEL)

import city_segmenters_code as c
g  = c.PROVIDERS.get("gemini", {})
gp = c.PROVIDERS.get("gemini-pro", {})
print("gemini     model=", g.get("model"))
print("gemini-pro model=", gp.get("model"))
print("Both distinct:", g.get("model") != gp.get("model"))
