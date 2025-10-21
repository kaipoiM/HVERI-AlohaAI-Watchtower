from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.chains.summarize import load_summarize_chain
from langchain.prompts import PromptTemplate
from langchain.agents import Tool, Agent, AgentType
from langchain.tools import BaseTool
from langchain_openai import ChatOpenAI
from langchain.schema.output_parser import StrOutputParser
from pydantic import BaseModel, Field
from typing import Optional, Type

from fpdf import FPDF
from datetime import datetime
from dotenv import load_dotenv, dotenv_values
import os, sys

# variables for API key and language model
load_dotenv()
four_key = os.getenv("OPENAI_KEY")
cookiesFile = os.getenv("COOKIES")
llm = ChatOpenAI(model='gpt-4', openai_api_key=four_key, temperature='0')

# variable to store timestamp of program run
now = datetime.now()
timestamp = now.strftime("%m-%d-%Y %H:%M\n")
file_timestamp = now.strftime("%m-%d-%Y_%H:%M\n")


# test for agent tools (no diacreticals used)
# def mapDistrict(town_name: str) -> str:
#     """Useful for determining what district the commment is coming from,
#         if a town is named in the comment, correlate it to the district"""
#     district_to_town = {
#     "North Kohala": ["Halaula", "Hawi", "Kapaau", "Puakea Ranch", "Mahukona", "Kaholena", "Kohala Ranch", "Upolu", "Halawa", "Makapala", "Niulii", "Pulolu"],
#     "South Kohala": ["Kawaihae", "Hapuna", "Puako", "Waikoloa", "Waimea", "Waikii", "Puukapu"],
#     "Hamakua": ["Waipio", "Kukuihaele", "Ahualoa", "Honokaa", "Paauhau", "Kalopa", "Paauilo", "Kukuaiau", "Niupea"],
#     "North Hilo": ["Ookala", "Waipunalei", "Laupahoehoe", "Papaaloa", "Kapehu", "Pohakupuka", "Ninole", "Umauma"],
#     "South Hilo": ["Hakalau", "Honomu", "Pepeekeo", "Onomea", "Papaikou", "Paukaa", "Puueo", "Wainaku", "Keaukaha", "Panaewa", "Kaiwiki", "Piihonua", "Kaumana", "Sunrise Ridge", "Waiakea Uka"],
#     "Puna": ["Kurtistown", "Hawaiian Paradise Park", "HPP", "Hawaiian Acres", "Orchidland", "Hawaiian Beaches", "Ainaloa", "Nanawale Estates", "Kapoho", "Pohoiki", "Leilani Estates", "Opihikao", "Kehena", "Kaimu", "Mountain View", "Glenwood", "Fern Acres", "Volcano", "Kalapana"],
#     "Ka'u": ["Wood Valley", "Pahala", "Punaluu", "Naalehu", "Waiohinu", "Ka Lae", "Kamaoa", "Ocean View", "Manuka"],
#     "South Kona": ["Honomalino", "Milolii", "Papa Bay", "Kona", "Hookena", "Kealia", "Honaunau", "Keei", "Napoopoo", "Captain Cook", "Kealakekua",],
#     "North Kona": ["Honalo", "Keauhou", "Alii Heights", "Hualalai", "Kailua-Kona", "Kealakehe", "Kaloko", "Makalawena", "Holulaloa", "Kaupulehu", "Kukio", "Puulani Ranch", "Makalei Estates"]
# }

#     for district, towns in district_to_town.items():
#         if town_name in towns:
#             return district

# tools = [
#     Tool(
#         name = "districtMap",
#         func=mapDistrict,
#         description="context for when a comment states what subdivision they are from and what district it is located in"

#     )
# ]
# class DistrictToTownInput(BaseModel):
#     """Input for District to Town check"""
#     town_in: str = Field(..., description="Town input for model")
# class DistrictToTownTool(BaseTool):
#     name = "map_destrict"
#     description = "Useful for determining what district the commment is coming from, if a town is named in the comment, correlate it to the district"

#     def _run(self, town_in: str):
#         print("i'm running")
#         district_response = mapDistrict(town_in)
#         return district_response

#     def _arun(self, town_in: str):
#         raise NotImplementedError("This tool does not support async")

#     args_schema: Optional[Type[BaseModel]] = DistrictToTownInput

# open_ai_agent = Agent(tools, llm, agent=AgentType.OPENAI_FUNCTIONS, verbose=True)

# def run_agent_test():
#     open_ai_agent.run("What is the district of Kurtistown?")


def from_full():
    # specify file here
    # synthetic data: Sample_Data_synthetic_-_Waikoloa_fire.txt
    # test post data: full_comments.txt
    comments_text = "./full_comments.txt"
    with open(comments_text, 'r', encoding="utf8") as file:
        comments = file.read()

    # split file into docs
    text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(chunk_size=2000, chunk_overlap=0)
    docs = text_splitter.create_documents([comments])
    num_docs = len(docs)
    print("Full Comments have been split to " + str(num_docs) + " docs")

    # output number of tokens in each doc
    for doc in docs:
        num_tokens_curr_doc = llm.get_num_tokens(doc.page_content)
        print(num_tokens_curr_doc)

    map_prompt = """
            Topic: Natural Disaster
            For Audience: Hawaii County Civil Defense
            For Audience: Emergency Operations Center
            The following is a set of comments taken from a Facebook Group focusing on natural disasters on the island
            of Hawaii:

    {text}

            Organize each comment to the different districts of the Big Island (South Kohala, North Kohala, Hamakua, North Hilo, South Hilo, Puna, Ka'u, South Kona, and North Kona). 
            Use this context for each town corresponding to the district:
            - North Kohala: "Halaula", "Hawi", "Kapaau", "Puakea Ranch", "Mahukona", "Kaholena", "Kohala Ranch", "Upolu", "Halawa", "Makapala", "Niulii", "Pulolu"
            - South Kohala: "Kawaihae", "Hapuna", "Puako", "Waikoloa", "Waimea", "Waikii", "Puukapu"
            - Hamakua: "Waipio", "Kukuihaele", "Ahualoa", "Honokaa", "Paauhau", "Kalopa", "Paauilo", "Kukuaiau", "Niupea"
            - North Hilo: "Ookala", "Waipunalei", "Laupahoehoe", "Papaaloa", "Kapehu", "Pohakupuka", "Ninole", "Umauma"
            - South Hilo: "Hakalau", "Honomu", "Pepeekeo", "Onomea", "Papaikou", "Paukaa", "Puueo", "Wainaku", "Keaukaha", "Panaewa", "Kaiwiki", "Piihonua", "Kaumana", "Sunrise Ridge", "Waiakea Uka"
            - Puna: "Kurtistown", "Hawaiian Paradise Park", "HPP", "Hawaiian Acres", "Orchidland", "Hawaiian Beaches", "Ainaloa", "Nanawale Estates", "Kapoho", "Pohoiki", "Leilani Estates", "Opihikao", "Kehena", "Kaimu", "Mountain View", "Glenwood", "Fern Acres", "Volcano", "Kalapana"
            - Ka'u: "Wood Valley", "Pahala", "Punaluu", "Naalehu", "Waiohinu", "Ka Lae", "Kamaoa", "Ocean View", "Manuka"
            - South Kona: "Honomalino", "Milolii", "Papa Bay", "Kona", "Hookena", "Kealia", "Honaunau", "Keei", "Napoopoo", "Captain Cook", "Kealakekua"
            - North Kona: "Honalo", "Keauhou", "Alii Heights", "Hualalai", "Kailua-Kona", "Kealakehe", "Kaloko", "Makalawena", "Holulaloa", "Kaupulehu", "Kukio", "Puulani Ranch", "Makalei Estates"

            In another list, organize the most urgent comments (comments that show impact on human safety and access to essential services)
    """
    map_prompt_template = PromptTemplate(template=map_prompt, input_variables=["text"])

    combine_prompt = """
                Topic: Natural Disaster
                For Audience: Hawaii County Civil Defense
                For Audience: Emergency Operations Center
                The following is a set of comments taken from a Facebook Group focusing on natural disasters on the island
                of Hawaii.

                {text}

                With these organized comments create a professional natural disaster report with this specific format:

                Format:
                1) Most Affected Areas 
                        - List the areas that were experiencing the most negative effects
                2) Reports by District
                        - Write a 3 sentence summary about each district
                3) High-Priority Events
                        - List the comment (comments that showed the most negative impact on human safety and access to essential services) and a short explanation why it was highlighted with urgency 
                """
    combine_prompt_template = PromptTemplate(template=combine_prompt, input_variables=["text"])

    chain = load_summarize_chain(llm=llm, chain_type='map_reduce',
                                 map_prompt=map_prompt_template,
                                 combine_prompt=combine_prompt_template,
                                 verbose=True
                                 )

    # llm.smith.evaluation.progress.ProgressBarCallback()
    output = chain.run(docs)

    # Writing GPT's output to text file, then opening it for reading
    with open('finalreport.txt', 'w') as f:
        f.write(timestamp)
        f.write(output.strip())
    f.close()


def combine_reports():
    report1 = input("Enter name of first report\n")
    report2 = input("Enter name of second report\n")

    filenames = [report1, report2]

    with open("mergedfile.txt", 'w', encoding="utf8") as file:
        for fname in filenames:
            index = filenames.index(fname)
            index = index + 1
            file.write("Report " + str(index) + ":\n\n")
            with open(fname) as infile:
                for line in infile:
                    file.write(line)
            file.write("\n\n")

    # specify file here
    comments_text = "mergedfile.txt"
    with open(comments_text, 'r', encoding="utf8") as file:
        comments = file.read()

    # split file into docs [num_docs is len(docs)]
    text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(chunk_size=3000, chunk_overlap=0)
    docs = text_splitter.create_documents([comments])
    num_docs = len(docs)
    print("Reports have been split to " + str(num_docs) + " docs")

    # output number of tokens in each doc
    for doc in docs:
        num_tokens_curr_doc = llm.get_num_tokens(doc.page_content)
        print(num_tokens_curr_doc)

    # applying a prompt to each chunk of text
    map_prompt = """
            Topic: Natural Disaster
            For Audience: Hawaii County Civil Defense
            For Audience: Emergency Operations Center
            The following is two reports with three sections: Most Affected Areas, Reports by District, and High-Priority Events

    {text}

            Please combine these two reports into one report with the same three sections

            PRE-SUMMARY:
    """
    map_prompt_template = PromptTemplate(template=map_prompt, input_variables=["text"])

    # prompt to combine all chunks
    combine_prompt = """
            Topic: Natural Disaster
            For Audience: Hawaii County Civil Defense
            For Audience: Emergency Operations Center
            The following is two reports with three sections: Most Affected Areas, Reports by District, and High-Priority Events

    {text}

            Please combine these two reports into one report with the same three sections.
            You should produce a final report with this specific format:

                Format:
                1) Most Affected Areas 
                        -list separated by commas
                2) Reports by District
                        -list every location in each district with a 3 sentence summary on each location. 
                If it is not a location in a district in the county of Hawaii, list it under 'Other'.
                3) High-Priority Events
                        -Use quotes from the individual reports in their full context.

                Format this report as if you are writing in a Word Document
            """
    combine_prompt_template = PromptTemplate(template=combine_prompt, input_variables=["text"])

    chain = load_summarize_chain(llm=llm, chain_type='map_reduce',
                                 map_prompt=map_prompt_template,
                                 combine_prompt=combine_prompt_template,
                                 verbose=True
                                 )

    # llm.smith.evaluation.progress.ProgressBarCallback()
    output = chain.run(docs)

    # Writing GPT's output to text file, then opening it for reading
    with open('finalreport.txt', 'w') as f:
        f.write(timestamp)
        f.write(output.strip())


def write_report():
    f = open("finalreport.txt", "r")

    # Formatting PDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Times", size=10)

    # Putting each line from file into a "multi-line cell"
    for x in f:
        pdf.multi_cell(w=190, h=5, txt=x.strip(), align='L')
    pdf.output("OutputReport_" + file_timestamp + ".pdf")
    f.close()

    print("Report generated.")
    input("Press Enter to exit.")