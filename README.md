# SUB AREA MAPPER

An AI-powered multi-agent system that automatically discovers commercial zones, business districts, industrial areas, and companies across countries and cities using Large Language Models (LLMs), Tavily Search, and Supabase.

The system is designed as a distributed swarm of specialized AI agents that collaboratively build a structured business location database.

---

# Overview

SUB AREA MAPPER is a scalable multi-agent data collection pipeline that:

- Reads countries from Supabase
- Discovers major cities
- Classifies city importance
- Finds commercial zones
- Estimates business density
- Extracts companies
- Stores structured data in Supabase

The project follows a modular architecture where each sub-agent performs one specialized task.

---

# Architecture

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

# Features

## Agent 1

- Reads countries from database
- Creates work batches
- Launches swarm workers

---

## Agent 2

Discovers cities using

- Tavily Search
- Groq LLM
- Gemini
- OpenAI

Classifies cities into

- Metro
- Tier 1
- Tier 2
- Tier 3

Stores results in Supabase.

---

## Agent 3

Discovers

- CBDs
- Industrial Estates
- SEZs
- IT Parks
- Business Districts
- Commercial Clusters

Uses a two-pass architecture

### Pass 1

Zone discovery

### Pass 2

Business count estimation

Business count is obtained through

- Regex extraction
- LLM extraction
- LLM estimation

Zones are ranked by business density.

---

## Agent 4

Finds companies operating inside discovered zones.

Stores

- Company Name
- Category
- Priority
- Source URL

---

# Tech Stack

| Technology | Purpose |
|------------|---------|
| Python | Backend |
| Supabase | Database |
| Tavily | Web Search |
| Groq | LLM |
| Gemini | LLM |
| OpenAI | LLM |
| Requests | API Communication |
| dotenv | Environment Variables |
| JSON | Structured Data |

---

# Project Structure

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

# Database

## Countries

```
id
country_name
iso3
```

---

## Cities

```
id
city_name
country_name
city_type
priority
```

---

## Zones

```
id
zone_name
city_name
country_name
business_count
count_source
rank
source_url
```

---

## Companies

```
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

# Environment Variables

```
SUPABASE_URL=

SUPABASE_KEY=

TAVILY_API_KEY=

GROQ_API_KEY=

GEMINI_API_KEY=

OPENAI_API_KEY=
```

---

# Installation

Clone the repository

```
git clone <repository_url>
```

Create virtual environment

```
python -m venv venv
```

Activate

Windows

```
venv\Scripts\activate
```

Linux

```
source venv/bin/activate
```

Install dependencies

```
pip install -r requirements.txt
```

---

# Running

Agent 2

```
python swarm.py
```

Agent 3

```
python swarm_zone_finder.py
```

---

# Workflow

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

# Output

The system produces

- Structured city database
- Commercial zones
- Ranked business districts
- Company database
- JSON snapshots
- Supabase records

---

# Error Handling

The project includes

- Retry mechanisms
- Duplicate detection
- API failure recovery
- Exponential backoff
- Structured logging
- Swarm worker isolation

---

# Future Improvements

- Google Maps integration
- Live business verification
- Incremental database updates
- Business trend analysis
- AI confidence scoring
- Dashboard visualization

---

# Contributors

Developed as part of an AI Engineering Internship Project.
