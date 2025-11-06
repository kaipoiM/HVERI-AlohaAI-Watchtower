import anthropic
from fpdf import FPDF
from datetime import datetime
from dotenv import load_dotenv
import os
import json

# Load environment variables
load_dotenv()
claude_api_key = os.getenv("ANTHROPIC_API_KEY")

# Initialize Claude client
client = anthropic.Anthropic(api_key=claude_api_key)

# Variable to store timestamp of program run
now = datetime.now()
timestamp = now.strftime("%m-%d-%Y %H:%M\n")
file_timestamp = now.strftime("%m-%d-%Y_%H:%M")


def split_text(text, max_chars=15000):
    """Split text into chunks that fit within Claude's context window"""
    chunks = []
    current_chunk = ""

    lines = text.split('\n')
    for line in lines:
        if len(current_chunk) + len(line) < max_chars:
            current_chunk += line + '\n'
        else:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = line + '\n'

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def call_claude(prompt, max_tokens=4096):
    """Make a call to Claude API"""
    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=max_tokens,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        return message.content[0].text
    except Exception as e:
        print(f"Error calling Claude: {e}")
        return None


def from_full():
    """Process full comments file and generate disaster report"""
    # Specify file here
    comments_json = "../Graph API/comments2.json"

    try:
        with open(comments_json, 'r', encoding="utf8") as file:
            comments_data = json.load(file)

        # Format comments with timestamps
        comments = ""
        for entry in comments_data:
            timestamp = entry.get("timestamp", "No timestamp")
            comment = entry.get("comment", "")
            comments += f"[{timestamp}] {comment}\n\n"
    except FileNotFoundError:
        print(f"Error: {comments_json} not found")
        return
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON file: {e}")
        return

    # Split file into chunks
    chunks = split_text(comments, max_chars=15000)
    num_chunks = len(chunks)
    print(f"Full Comments have been split to {num_chunks} chunks")

    # Process each chunk with map prompt
    map_prompt_template = """
<task>Organize Facebook comments by geographic district</task>

<context>
<topic>Natural Disaster</topic>
<source>Facebook Group comments about natural disasters on Hawaii Island</source>
</context>

<input_data>
{text}
</input_data>

<districts>
<district name="North Kohala">Halaula, Hawi, Kapaau, Puakea Ranch, Mahukona, Kaholena, Kohala Ranch, Upolu, Halawa, Makapala, Niulii, Pulolu</district>
<district name="South Kohala">Kawaihae, Hapuna, Puako, Waikoloa, Waimea, Waikii, Puukapu</district>
<district name="Hamakua">Waipio, Kukuihaele, Ahualoa, Honokaa, Paauhau, Kalopa, Paauilo, Kukuaiau, Niupea</district>
<district name="North Hilo">Ookala, Waipunalei, Laupahoehoe, Papaaloa, Kapehu, Pohakupuka, Ninole, Umauma</district>
<district name="South Hilo">Hakalau, Honomu, Pepeekeo, Onomea, Papaikou, Paukaa, Puueo, Wainaku, Keaukaha, Panaewa, Kaiwiki, Piihonua, Kaumana, Sunrise Ridge, Waiakea Uka</district>
<district name="Puna">Kurtistown, Hawaiian Paradise Park, HPP, Hawaiian Acres, Orchidland, Hawaiian Beaches, Ainaloa, Nanawale Estates, Kapoho, Pohoiki, Leilani Estates, Opihikao, Kehena, Kaimu, Mountain View, Glenwood, Fern Acres, Volcano, Kalapana</district>
<district name="Ka'u">Wood Valley, Pahala, Punaluu, Naalehu, Waiohinu, Ka Lae, Kamaoa, Ocean View, Manuka</district>
<district name="South Kona">Honomalino, Milolii, Papa Bay, Kona, Hookena, Kealia, Honaunau, Keei, Napoopoo, Captain Cook, Kealakekua</district>
<district name="North Kona">Honalo, Keauhou, Alii Heights, Hualalai, Kailua-Kona, Kealakehe, Kaloko, Makalawena, Holulaloa, Kaupulehu, Kukio, Puulani Ranch, Makalei Estates</district>
</districts>

<instructions>
1. Organize each comment by district based on location mentioned
2. Create a separate list of urgent comments that show:
   - Direct impact on human safety
   - Impact on essential services (roads, power, water)
   - Active emergencies requiring immediate attention
3. EXCLUDE routine maintenance, scheduled work, or non-emergency information
</instructions>

<output_format>
Return organized data in a simple text format by district, followed by urgent items list.
</output_format>
"""

    print("Processing chunks with Claude...")
    organized_chunks = []
    for i, chunk in enumerate(chunks):
        print(f"Processing chunk {i + 1}/{num_chunks}...")
        map_prompt = map_prompt_template.format(text=chunk)
        result = call_claude(map_prompt)
        if result:
            organized_chunks.append(result)

    # Combine all organized chunks
    combined_text = "\n\n".join(organized_chunks)

    # Create final report with combine prompt
    combine_prompt = f"""
<task>Create a professional Facebook post for emergency updates</task>

<audience>
<primary>Hawaii County Civil Defense</primary>
<secondary>Emergency Operations Center</secondary>
<platform>Facebook</platform>
</audience>

<input_data>
{combined_text}
</input_data>

<strict_requirements>
<requirement>Use professional tone appropriate for civil defense</requirement>
<requirement>Include ONLY areas with actual incidents or emergencies</requirement>
<requirement>EXCLUDE districts with no reported issues</requirement>
<requirement>Keep post concise</requirement>
<requirement>Use bullet points or short paragraphs for readability</requirement>
<requirement>Start with brief situation overview</requirement>
<requirement>ONLY include information about active emergencies, NOT routine activities</requirement>
</strict_requirements>

<format_structure>
<opening>Brief timestamp and situation summary (1-2 sentences)</opening>
<affected_areas>List ONLY districts with active incidents (bullet points)</affected_areas>
<priority_items>Highlight immediate safety concerns if any exist</priority_items>
<closing>Brief closing statement with contact info reminder</closing>
</format_structure>

<exclusions>
- Do NOT include districts with no incidents
- Do NOT include "All systems normal" statements
- Do NOT include routine maintenance unless it affects emergency access
- Do NOT use formal report headers like "PRIORITY 1" or numbered sections
- Do NOT create a lengthy formatted report structure
</exclusions>

<example_tone>
"We're monitoring [number] active situations across Hawaii Island. [Brief description]. Stay safe and check back for updates."
</example_tone>
"""

    print("Generating final report...")
    output = call_claude(combine_prompt, max_tokens=8000)

    if output:
        # Write output to text file
        with open('finalreport.txt', 'w', encoding='utf-8') as f:
            f.write(timestamp)
            f.write(output.strip())
        print("Report written to finalreport.txt")
    else:
        print("Failed to generate report")


def combine_reports():
    """Combine two existing reports into one"""
    report1 = input("Enter name of first report: ")
    report2 = input("Enter name of second report: ")

    filenames = [report1, report2]

    try:
        with open("mergedfile.txt", 'w', encoding="utf8") as file:
            for fname in filenames:
                index = filenames.index(fname) + 1
                file.write(f"Report {index}:\n\n")
                with open(fname, encoding="utf8") as infile:
                    file.write(infile.read())
                file.write("\n\n")
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return

    # Read merged file
    with open("mergedfile.txt", 'r', encoding="utf8") as file:
        comments = file.read()

    # Split into chunks if needed
    chunks = split_text(comments, max_chars=20000)
    num_chunks = len(chunks)
    print(f"Reports have been split to {num_chunks} chunks")

    # Process chunks
    map_prompt_template = """
<task>Combine two Facebook posts into one</task>

<context>
<topic>Natural Disaster Updates</topic>
<source>Two existing Facebook posts from Hawaii County Civil Defense</source>
</context>

<input_data>
{text}
</input_data>

<instructions>
1. Combine information from both posts
2. Remove duplicate information
3. Maintain chronological order of events
4. Keep only active emergencies and incidents
5. Preserve the Facebook post format
</instructions>

<output_format>
Return a single combined text with all incidents organized by district.
</output_format>
"""

    organized_chunks = []
    for i, chunk in enumerate(chunks):
        print(f"Processing chunk {i + 1}/{num_chunks}...")
        map_prompt = map_prompt_template.format(text=chunk)
        result = call_claude(map_prompt)
        if result:
            organized_chunks.append(result)

    # Combine all organized chunks
    combined_text = "\n\n".join(organized_chunks)

    # Create final combined report
    combine_prompt = f"""
<task>Create a professional Facebook post combining two emergency updates</task>

<audience>
<primary>Hawaii County Civil Defense</primary>
<secondary>Emergency Operations Center</secondary>
<platform>Facebook</platform>
</audience>

<input_data>
{combined_text}
</input_data>

<strict_requirements>
<requirement>Combine incidents from both reports without duplication</requirement>
<requirement>Use professional tone appropriate for civil defense</requirement>
<requirement>Include ONLY areas with actual incidents or emergencies</requirement>
<requirement>EXCLUDE districts with no reported issues</requirement>
<requirement>Keep post concise</requirement>
<requirement>Use bullet points or short paragraphs for readability</requirement>
<requirement>Start with brief situation overview</requirement>
<requirement>ONLY include information about active emergencies, NOT routine activities</requirement>
</strict_requirements>

<format_structure>
<opening>Brief timestamp and situation summary (1-2 sentences)</opening>
<affected_areas>List ONLY districts with active incidents (bullet points)</affected_areas>
<priority_items>Highlight immediate safety concerns if any exist</priority_items>
<closing>Brief closing statement with contact info reminder</closing>
</format_structure>

<exclusions>
- Do NOT include districts with no incidents
- Do NOT include "All systems normal" statements
- Do NOT include routine maintenance unless it affects emergency access
- Do NOT use formal report headers like "PRIORITY 1" or numbered sections
- Do NOT create a lengthy formatted report structure
- Do NOT list every location in each district
</exclusions>

<example_tone>
"Update as of [time]: We're monitoring [number] active situations across Hawaii Island. [Brief description]. Stay safe and check back for updates."
</example_tone>
"""

    print("Generating combined report...")
    output = call_claude(combine_prompt, max_tokens=8000)

    if output:
        # Write output to text file
        with open('finalreport.txt', 'w', encoding='utf-8') as f:
            f.write(timestamp)
            f.write(output.strip())
        print("Combined report written to finalreport.txt")
    else:
        print("Failed to generate combined report")


def write_report():
    """Convert text report to PDF"""
    try:
        f = open("finalreport.txt", "r", encoding="utf-8")
    except FileNotFoundError:
        print("Error: finalreport.txt not found. Generate a report first.")
        return

    # Formatting PDF - use Unicode font
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)  # Arial has better Unicode support than Times

    # Putting each line from file into a "multi-line cell"
    for line in f:
        # Replace problematic Unicode characters for PDF compatibility
        safe_line = line.strip()
        # Replace Hawaiian characters with closest ASCII equivalents if needed
        # Or skip lines that cause issues
        try:
            pdf.multi_cell(w=190, h=5, txt=safe_line, align='L')
        except UnicodeEncodeError:
            # If line has unsupported characters, try to encode safely
            safe_line = safe_line.encode('ascii', 'ignore').decode('ascii')
            pdf.multi_cell(w=190, h=5, txt=safe_line, align='L')

    output_filename = f"OutputReport_{file_timestamp.replace(':', '-')}.pdf"
    pdf.output(output_filename)
    f.close()

    print(f"Report generated: {output_filename}")


def main():
    """Main menu"""
    print("=" * 50)
    print("Natural Disaster Report Generator (Claude Version)")
    print("=" * 50)
    print("\nOptions:")
    print("1. Generate report from full comments")
    print("2. Combine two existing reports")
    print("3. Convert finalreport.txt to PDF")
    print("4. Exit")

    choice = input("\nEnter your choice (1-4): ")

    if choice == "1":
        from_full()
        write_pdf = input("\nGenerate PDF? (y/n): ")
        if write_pdf.lower() == 'y':
            write_report()
    elif choice == "2":
        combine_reports()
        write_pdf = input("\nGenerate PDF? (y/n): ")
        if write_pdf.lower() == 'y':
            write_report()
    elif choice == "3":
        write_report()
    elif choice == "4":
        print("Exiting...")
        return
    else:
        print("Invalid choice")

    input("\nPress Enter to exit.")


if __name__ == "__main__":
    main()