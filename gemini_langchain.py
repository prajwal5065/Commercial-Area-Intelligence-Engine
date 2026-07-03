# gemini_langchain.py
# pip install langchain langchain-google-genai google-generativeai

import google.generativeai as genai
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

API_KEY = "AQ.Ab8RN6Lnd6kSpFJ-TmtOrLSres5UFMVfzzvOeQjHfh4lJzDfUw"  # paste your key here

# ── 1. List all available models ─────────────────────────────────────────────
print("=" * 60)
print("AVAILABLE GEMINI MODELS")
print("=" * 60)

genai.configure(api_key=API_KEY)

chat_models = []
embed_models = []
other_models = []

for m in genai.list_models():
    name = m.name.replace("models/", "")
    methods = list(m.supported_generation_methods)

    if "generateContent" in methods:
        chat_models.append(name)
    elif "embedContent" in methods:
        embed_models.append(name)
    else:
        other_models.append(name)

print(f"\n💬 Chat / Generation models ({len(chat_models)}):")
for m in chat_models:
    print(f"   • {m}")

print(f"\n🔢 Embedding models ({len(embed_models)}):")
for m in embed_models:
    print(f"   • {m}")

if other_models:
    print(f"\n📦 Other models ({len(other_models)}):")
    for m in other_models:
        print(f"   • {m}")

# ── 2. Test a chat model via LangChain ───────────────────────────────────────
print("\n" + "=" * 60)
print("TESTING CHAT MODEL (gemini-2.5-flash)")
print("=" * 60)

try:
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=API_KEY,
        temperature=0.3,
    )
    response = llm.invoke("Say hello in one sentence.")
    print(f"\n✅ Response: {response.content}")
except Exception as e:
    print(f"\n❌ Chat model error: {e}")

# ── 3. Test an embedding model via LangChain ─────────────────────────────────
print("\n" + "=" * 60)
print("TESTING EMBEDDING MODEL (models/embedding-001)")
print("=" * 60)

try:
    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/embedding-001",
        google_api_key=API_KEY,
    )
    vector = embeddings.embed_query("Hello world")
    print(f"\n✅ Embedding dims: {len(vector)}")
    print(f"   First 5 values : {[round(v, 4) for v in vector[:5]]}")
except Exception as e:
    print(f"\n❌ Embedding model error: {e}")

print("\n" + "=" * 60)
print("Done.")
print("=" * 60)