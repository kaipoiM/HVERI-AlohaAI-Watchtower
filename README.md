# AlohaAI Watchtower

**AI-Powered Emergency Response Intelligence for Hawaii**

---

## Overview

AlohaAI Watchtower is an emergency response tool developed for Hawaii County Civil Defense that monitors social media during natural disasters. It automatically analyzes community-sourced observations from the Hawaii Tracker Facebook group (172k+ members) and generates organized intelligence reports for emergency coordinators.

## What It Does

During emergencies like wildfires, floods, or volcanic events, the system:

1. **Scrapes** comments from Facebook posts every 30 minutes
2. **Organizes** reports by geographic district (9 Big Island districts)
3. **Identifies** high-priority threats to public safety
4. **Generates** professional summaries for emergency operations centers
5. **Tracks** changes between runs to surface emerging trends

## Quick Start

```bash
# Install dependencies
pip install anthropic requests python-dotenv fpdf kivy

# Configure .env file
FACEBOOK_ACCESS_TOKEN=your_token
HAWAII_TRACKER_GROUP_ID=your_group_id
ANTHROPIC_API_KEY=your_api_key

# Run the application
python AlohaAIWatchtower.py
```

## Output Format

Reports include:
- **Most Affected Areas** - Districts ranked by severity
- **Reports by District** - 3-sentence summaries of each area
- **High-Priority Events** - Urgent items with urgency rationale

Exports available in: TXT, PDF, JSON, CSV

## Use Case

1. HVERI posts monitoring request to Hawaii Tracker during incident
2. Community members comment with real-time observations
3. System analyzes comments every 30 minutes
4. Emergency coordinators receive actionable intelligence organized by location
5. Response teams prioritize based on high-priority event list

---

**Developed by:** Kaipo'i Murray, Noah Gamble, Matthew Seuh  
**For:** Hawaiian Volcano Education & Resilience Institute (HVERI)  
**Contact:** dane@hveri.org