# Paper Selection Tool for NeurIPS

This tool helps you identify interesting papers and authors from NeurIPS conferences by analyzing submissions on OpenReview and filtering them based on your research interests using AI.

## Overview

The `main_select_interesting_papers.py` script:
1. Fetches all paper submissions from OpenReview for a specified conference
2. Extracts paper metadata (title, abstract) and author information (including PhD student status and location)
3. Uses ChatGPT to evaluate each paper's relevance to your research keywords
4. Processes author alma mater locations to categorize PhD students by region
5. Writes relevant papers and authors to a Google Sheet for easy review

## Prerequisites

### 1. Python Environment

- Python 3.8 or higher
- A virtual environment is recommended (there's already a `venv/` folder in this project)

### 2. Required Python Packages

Install dependencies using pip:

```bash
# Activate the virtual environment (if using the existing venv)
source venv/bin/activate  # On macOS/Linux
# or
venv\Scripts\activate  # On Windows

# Install required packages
pip install openreview openai anthropic tqdm picklecachefunc
```

You may also need:
- `gsheet_manager` (for Google Sheets integration)
- Other dependencies as needed

### 3. API Credentials

#### OpenReview Account
You need an OpenReview account with access to the conference submissions:
- Set environment variables:
  ```bash
  export OPENREVIEW_USERNAME="your_username"
  export OPENREVIEW_PASSWORD="your_password"
  ```

#### OpenAI API Key
The script uses ChatGPT (gpt-4.1) to evaluate paper relevance:
- Set environment variable:
  ```bash
  export OPENAI_API_KEY="your_openai_api_key"
  ```

#### Google Sheets Credentials
You need a Google Cloud service account JSON key file:
- The script expects a file named `inner-bridge-282608-030fbb66c110.json` in the project root
- This file should contain Google Cloud service account credentials with Google Sheets API access
- Make sure the service account has permission to create/edit the Google Sheet

## Configuration

### Step 1: Add NeurIPS Configuration

Open `main_select_interesting_papers.py` and add NeurIPS to the `CONFERENCE_CONFIGS` dictionary (around line 328):

```python
CONFERENCE_CONFIGS = {
    # ... existing conferences ...
    "NeurIPS2025": {
        "CONFERENCE_ID": "NeurIPS.cc/2025/Conference",
        "CACHE_ROOT": "data/NeurIPS2025_NAVER_CANDIDATES",
        "GSHEET_TITLE": "NeurIPS 2025 people to meet",
    },
    # Add more conferences as needed
}
```

**Note**: Adjust the year (2025, 2026, etc.) and conference ID format as needed. The conference ID format for NeurIPS is typically `NeurIPS.cc/YYYY/Conference`.

### Step 2: Set Conference Name

In `main_select_interesting_papers.py`, change line 20:

```python
CONFERENCE_NAME = "NeurIPS2025"  # Change this to your target conference
```

### Step 3: Customize Research Keywords (Optional)

The script filters papers based on keywords defined around line 24. You can modify the `KEYWORDS` list to match your research interests:

```python
KEYWORDS = [
    "LLM",
    "VLM",
    "Security",
    # ... add or remove keywords as needed
]
```

### Step 4: Google Sheet Configuration

- **Sheet Name**: The script uses `"Sheet1"` by default (line 47). Change if needed.
- **Sheet Title**: This is automatically set based on the conference configuration (e.g., "NeurIPS 2025 people to meet")
- Make sure the Google Sheet exists or can be created by the service account

## Usage

### Basic Usage

1. **Activate the virtual environment** (if using):
   ```bash
   source venv/bin/activate
   ```

2. **Set environment variables**:
   ```bash
   export OPENREVIEW_USERNAME="your_username"
   export OPENREVIEW_PASSWORD="your_password"
   export OPENAI_API_KEY="your_api_key"
   ```

3. **Run the script**:
   ```bash
   python main_select_interesting_papers.py
   ```

### Debug Mode

To test with a smaller number of papers, set `DEBUG = True` on line 50:

```python
DEBUG = True  # Process only first 5 papers
```

This is useful for testing your setup before processing all papers.

## What the Script Does

1. **Fetches Papers**: Retrieves all submissions from OpenReview for the specified conference
2. **Extracts Metadata**: For each paper, extracts:
   - Paper ID, title, abstract
   - First author information (email, homepage, Google Scholar, affiliation)
   - PhD student status and location
3. **Evaluates Relevance**: Uses ChatGPT to check if each paper matches your research keywords
4. **Processes Locations**: Categorizes PhD student alma maters into regions (Europe, US, Korea, Asia, Other)
5. **Writes to Google Sheet**: Outputs relevant papers with author information to a Google Sheet

## Output

The script creates a Google Sheet with the following columns:
- `id`: OpenReview paper ID
- `title`: Paper title
- `abstract`: Paper abstract
- `Categories`: Comma-separated list of matching keywords
- `#Categories`: Number of matching categories
- `author_email`: First author's email
- `author_first_name`: First author's first name
- `author_last_name`: First author's last name
- `author_homepage`: First author's homepage URL
- `author_gscholar`: First author's Google Scholar profile
- `author_affiliation`: First author's affiliation/position history
- `author_is_student`: Boolean indicating if first author is a PhD student
- `author_phd_location`: Location category (Europe, US, Korea, Asia, Other, or N/A)

## Caching

The script uses caching to avoid redundant API calls:
- Paper data is cached in `data/{CONFERENCE_NAME}_NAVER_CANDIDATES/`
- ChatGPT responses are cached in `data/{CONFERENCE_NAME}_NAVER_CANDIDATES/gpt-4.1/`
- Alma mater location lookups are cached in `data/{CONFERENCE_NAME}_NAVER_CANDIDATES/alma_mater_individual/`

You can delete cache files to force re-processing, or the script will automatically use cached results when available.

## Troubleshooting

### Error: Conference not found
- Make sure you've added NeurIPS to `CONFERENCE_CONFIGS` with the correct format
- Check that `CONFERENCE_NAME` matches a key in `CONFERENCE_CONFIGS`

### Error: OpenReview authentication failed
- Verify your `OPENREVIEW_USERNAME` and `OPENREVIEW_PASSWORD` environment variables are set correctly
- Ensure your OpenReview account has access to the conference submissions

### Error: OpenAI API key not found
- Check that `OPENAI_API_KEY` environment variable is set
- Verify your API key is valid and has sufficient credits

### Error: Google Sheets access denied
- Ensure the service account JSON file exists and is correctly named
- Verify the service account has Google Sheets API enabled
- Check that the service account has permission to create/edit the target Google Sheet

### No papers found
- The conference submissions may not be available yet on OpenReview
- Check that the `CONFERENCE_ID` format is correct for the year you're targeting
- Verify your OpenReview account has access to view submissions

### Processing is slow
- The script processes papers one by one to avoid rate limits
- For large conferences (1000+ papers), this can take several hours
- Use `DEBUG = True` to test with a smaller subset first
- Results are cached, so re-running will be faster

## Notes

- The script processes papers sequentially to respect API rate limits
- ChatGPT API calls are cached, so re-running the script won't incur additional costs for already-processed papers
- The script focuses on the **first author** of each paper for author information
- Only papers with at least one matching keyword are included in the output Google Sheet

## Support

For issues or questions, please contact the script maintainer or refer to the code comments in `main_select_interesting_papers.py`.

