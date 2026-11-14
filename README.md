# EGSA Digital Equb Registration System

A web-based membership registration system built with Python,
Streamlit and Supabase PostgreSQL.

## Features

- Maximum 10 members per Equb group
- Automatic registration closure
- Live membership counter
- Duplicate phone number prevention
- Unique member numbers
- Administrator dashboard
- CSV and Excel export
- Registration status management
- Public registration URL for Telegram sharing

## Technology

- Python
- Streamlit
- Supabase PostgreSQL
- GitHub
- Streamlit Community Cloud

## Installation

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Database

Execute supabase_schema.sql in the Supabase SQL Editor.

## Configuration

Configure the following Streamlit secrets:

- SUPABASE_URL
- SUPABASE_ANON_KEY
- SUPABASE_SERVICE_ROLE_KEY
- ADMIN_PASSWORD

## Deployment

Deploy app.py through Streamlit Community Cloud.

## Important

The system manages registration only. It does not process
or hold member contributions.
