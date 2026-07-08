<div align="center">
  
  <a href="https://git.io/typing-svg">
    <img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=600&size=40&pause=1000&color=00FF99&center=true&vCenter=true&width=800&height=80&lines=OxiAI+-+Sub+Area+Mapper;AI-Powered+Discovery;Multi-Agent+Swarm+System" alt="Typing SVG" />
  </a>

  <p align="center">
    <strong>An AI-powered multi-agent system that automatically discovers commercial zones, business districts, industrial areas, and companies across countries and cities using Large Language Models (LLMs), Tavily Search, and Supabase.</strong>
  </p>
  
  <p align="center">
    The system is designed as a distributed swarm of specialized AI agents that collaboratively build a structured business location database.
  </p>

  <p align="center">
    <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
    <img src="https://img.shields.io/badge/Supabase-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white" alt="Supabase" />
    <img src="https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white" alt="Streamlit" />
    <img src="https://img.shields.io/badge/OpenAI-412991?style=for-the-badge&logo=openai&logoColor=white" alt="OpenAI" />
  </p>
</div>

---

## 🌟 Overview

SUB AREA MAPPER is a scalable multi-agent data collection pipeline that:

- 🌍 Reads countries from Supabase
- 🏙️ Discovers major cities
- 📊 Classifies city importance
- 🏭 Finds commercial zones
- 📈 Estimates business density
- 🏢 Extracts companies
- 💾 Stores structured data in Supabase

The project follows a modular architecture where each sub-agent performs one specialized task.

---

## 🏗️ Architecture

```
                 Countries
                     │
                     ▼
            ┌────────────────┐
            │   Agent 1      │
            │ Country Reader │
            └────────────────┘
                     │
                     ▼
            ┌────────────────┐
            │   Agent 2      │
            │ City Finder    │
            └────────────────┘
                     │
                     ▼
            ┌────────────────┐
            │   Agent 3      │
            │ Zone Finder    │
            └────────────────┘
                     │
                     ▼
            ┌────────────────┐
            │   Agent 4      │
            │ Company Finder │
            └────────────────┘
                     │
                     ▼
                 Supabase
```

---

## ✨ Features

### 🥇 Agent 1
- Reads countries from database
- Creates work batches
- Launches swarm workers

---

### 🥈 Agent 2
Discovers cities using:
- Tavily Search
- Groq LLM
- Gemini
- OpenAI

Classifies cities into:
- Metro
- Tier 1
- Tier 2
- Tier 3

Stores results in Supabase.

---

### 🥉 Agent 3
Discovers:
- CBDs
- Industrial Estates
- SEZs
- IT Parks
- Business Districts
- Commercial Clusters

Uses a two-pass architecture:
- **Pass 1:** Zone discovery
- **Pass 2:** Business count estimation

Business count is obtained through:
- Regex extraction
- LLM extraction
- LLM estimation

Zones are ranked by business density.

---

### 🏅 Agent 4
Finds companies operating inside discovered zones.

Stores:
- Company Name
- Category
- Priority
- Source URL

---

## 🛠️ Tech Stack

| Technology | Purpose | Badge |
|------------|---------|-------|
| **Python** | Backend | <img src="https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white" alt="Python" /> |
| **Supabase** | Database | <img src="https://img.shields.io/badge/Supabase-3ECF8E?style=flat&logo=supabase&logoColor=white" alt="Supabase" /> |
| **Tavily** | Web Search | <img src="https://img.shields.io/badge/Tavily-FF6F00?style=flat&logo=searxng&logoColor=white" alt="Tavily" /> |
| **Groq / Gemini / OpenAI** | LLMs | <img src="https://img.shields.io/badge/OpenAI-412991?style=flat&logo=openai&logoColor=white" alt="OpenAI" /> |
| **Requests** | API Communication | <img src="https://img.shields.io/badge/Requests-339933?style=flat&logo=node.js&logoColor=white" alt="Requests" /> |
| **dotenv** | Environment Variables | <img src="https://img.shields.io/badge/dotenv-E34F26?style=flat&logo=html5&logoColor=white" alt="Dotenv" /> |
| **JSON** | Structured Data | <img src="https://img.shields.io/badge/JSON-000000?style=flat&logo=json&logoColor=white" alt="JSON" /> |

---

## 📁 Project Structure

```
SUB_AREA_MAPPER/
│
├── SUB AGENT 1
│
├── SUB AGENT 2
│   ├── city_finder.py
│   ├── supabase_client.py
│   ├── swarm.py
│
├── SUB AGENT 3
│   ├── zone_finders_code.py
│   ├── supabase_client.py
│   ├── swarm_zone_finder.py
│
├── SUB AGENT 4
│
├── .env
│
└── README.md
```

---

## 🗄️ Database

### 🗺️ Countries
```sql
id
country_name
iso3
```

### 🏙️ Cities
```sql
id
city_name
country_name
city_type
priority
```

### 🏭 Zones
```sql
id
zone_name
city_name
country_name
business_count
count_source
rank
source_url
```

### 🏢 Companies
```sql
id
company_name
category
city_name
zone_name
country_name
priority
source_url
```

---

## 🔐 Environment Variables

```env
SUPABASE_URL=
SUPABASE_KEY=
TAVILY_API_KEY=
GROQ_API_KEY=
GEMINI_API_KEY=
OPENAI_API_KEY=
```

---

## 🚀 Installation

**1. Clone the repository**
```bash
git clone <repository_url>
```

**2. Create virtual environment**
```bash
python -m venv venv
```

**3. Activate environment**
- **Windows:**
  ```bash
  venv\Scripts\activate
  ```
- **Linux / Mac:**
  ```bash
  source venv/bin/activate
  ```

**4. Install dependencies**
```bash
pip install -r requirements.txt
```

---

## 🏃 Running the Code

**Master Dashboard:**
Navigate to `SUB_AREA_MAPPER/Master Agent` and run:
```bash
streamlit run Exp_Full_Dash.py
```
*(Note: `run_pipeline.py` is the main Master agent code!)*

**Agent 2:**
```bash
python swarm.py
```

**Agent 3:**
```bash
python swarm_zone_finder.py
```

---

## 🔄 Workflow

```
Countries
      │
      ▼
City Discovery
      │
      ▼
City Classification
      │
      ▼
Zone Discovery
      │
      ▼
Business Count
      │
      ▼
Company Discovery
      │
      ▼
Supabase Storage
```

---

## 📊 Output

The system produces:
- Structured city database
- Commercial zones
- Ranked business districts
- Company database
- JSON snapshots
- Supabase records

---

## 🛡️ Error Handling

The project includes:
- Retry mechanisms
- Duplicate detection
- API failure recovery
- Exponential backoff
- Structured logging
- Swarm worker isolation

---

## 🔮 Future Improvements

- [ ] Google Maps integration
- [ ] Live business verification
- [ ] Incremental database updates
- [ ] Business trend analysis
- [ ] AI confidence scoring
- [ ] Dashboard visualization

---

Till My Mind Works Fine....
