# Utility imports
import os
import time
from tqdm.auto import tqdm

# Web scraping imports
import requests
from bs4 import BeautifulSoup

# OpenAI API imports
import openai
import gradio as gr
import deepl

# DeepL API key
deepl_key =  os.environ.get('DEEPL_KEY')
translator = deepl.Translator(deepl_key)

### Open AI Setup
#create assistant
openai.api_key = os.environ.get('OPENAI_API_KEY')

# Instructions for the AI assistant
instructions = '''
You are HepsiburadAI, an AI assistant that will curate me a list of relevant items based on my shopping needs namely functions, styles, budget, etc. Understand what the customer is looking for and search for it through the Hepsiburada website. Try to do this every time the customer asks for it. Give a curated list with a least 5 items. Start your answer with:
```
[
{
 "item_id": 1,
 "item_name": "Name of the item",
 "why_chosen": "Reason the item is chosen",
 "search_query": "Search query you would use to find it on Hepsiburada"
},
{
 "item_id": 2,
 "item_name": "Name of the item",
 "why_chosen": "Reason the item is chosen",
 "search_query": "Search query you would use to find it on Hepsiburada"
},
...]
```
(always keep ```)
but the answer {
 "item_id": 1,
 "item_name": "Name of the item",
 "why_chosen": "Reason the item is chosen",
 "search_query": "Search query you would use to find it on Hepsiburada"
},
{
 "item_id": 2,
 "item_name": "Name of the item",
 "why_chosen": "Reason the item is chosen",
 "search_query": "Search query you would use to find it on Hepsiburada"
}
don't give it this way. Make sure you add the url and a picture of the product.
Follow up by a paragraph explaining your curation choices in the same manner a shopkeeper would talk to a customer (no bullet points). If asked to change some items, you must always start your answer with the updated curated list. Don't say you don't have web search authorization. Scrap it through Hepsiburada.
'''

# Create OpenAI client and assistant
client = openai.OpenAI(api_key=OPENAI_API_KEY)
assistant = client.beta.assistants.create(
    name="HepsiburadAI",
    instructions=instructions,
    model="gpt-3.5-turbo-1106",
)

# Create thread
thread = client.beta.threads.create()

# Function to send message to OpenAI assistant and wait for run to finish
def create_message_and_run(client, input_message, thread, assistant, wait_time=0.5):
    message = client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=input_message
    )
    run = client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=assistant.id,
    )
    # Wait till API responds
    while run.status == "queued" or run.status == "in_progress":
        run = client.beta.threads.runs.retrieve(
            thread_id=thread.id,
            run_id=run.id,
        )
        time.sleep(wait_time)
    messages = client.beta.threads.messages.list(thread_id=thread.id)
    return message, run, messages

# Function to extract JSON from response
def extract_json(response):
    if '```' in response:
        l = [i for i in response.split('```') if i!='']
        if len(l) >= 2:
            try:
                return l[1], eval(l[0])
            except (SyntaxError, ValueError):
                return response, []
        else:
            return response, []
    else:
        return response, []

# Function to get Amazon search results
def get_amazon_search_results(search_query):
    output = search_query.replace(" ", "+")
    base_url = "https://www.hepsiburada.com/ara?q=" + output
    response = requests.get(base_url)
    soup = BeautifulSoup(response.text, 'html.parser')
    products = soup.find_all('li', class_='productListContent-zAP0Y5msy8OHn5z7T_K_')
    results = []
    for product in products:
        product_link = product.find('a', {'class': 'moria-ProductCard-gyqBb'})
        product_url = product_link['href'] if product_link and 'href' in product_link.attrs else 'URL not found'
        if product_url and not product_url.startswith('http'):
            product_url = f"https://www.hepsiburada.com{product_url}"
        name_tag = product.find('h3', {'data-test-id': 'product-card-name'})
        name = name_tag.get_text(strip=True) if name_tag else 'Name not found'
        image_url_tag = product.find('noscript')
        image_url = image_url_tag.img['src'] if image_url_tag and image_url_tag.img else 'Image not found'
        price_info = product.find('div', {'data-test-id': 'price-current-price'})
        price = price_info.get_text(strip=True) if price_info else 'Price not found'
        results.append({
            "image_url": image_url,
            "url": product_url,
            "price": price
        })
    return results

# Function to add scraped info to curated list
def add_amazon_info(curated_items):
    for item in tqdm(curated_items):
        print(item['item_name'])
        search_results = get_amazon_search_results(item['search_query'])
        print(search_results)
        for x in range(len(search_results)):
            item['image_url'] = search_results[x]['image_url']
            item['url'] = search_results[x]['url']
            item['price'] = search_results[x]['price']
    return curated_items

# Function to convert price to string
def priceToString(item):
    try:
        price = item["price"]
        return f"{price} "
    except:
        return ""

# Function for multiple replacements in text
def multiple_replace(text, replacements):
    text = str(text)
    for old, new in replacements.items():
        text = text.replace(old, new)
    price_new = text[:-2] +'.' +text[-2:]
    price_new = float(price_new)
    return price_new

# Replacements dictionary
replacements = {
    "TL": "",
    ",": "",
    ".": ""
}

# Function to beautify curated items
def beautify_curated_items(curated_items):
    curated_items = add_amazon_info(curated_items)
    total_price = '{:,}'.format(sum([multiple_replace(i.get('price', 0), replacements) for i in curated_items]))
    return f'\n\n<b>Curated List ({total_price} TL):</b>\n' + \
           '\n'.join([f'[{i["item_name"]}]({i.get("url", "Sold out")}) - \
                      {priceToString(i)} - \
                      {i["why_chosen"]}\
                      <img src = {i.get("image_url", "")}>' for i in curated_items])

# Global variables to keep track of curated items and image generation prompt
curated_items = []
image_generation_response=""

# Function for chat interaction
def chat(input_message):
    global curated_items
    global image_generation_response
    _, _, messages = create_message_and_run(client, input_message, thread, assistant)
    response = messages.data[0].content[0].text.value
    print(response)
    response, new_curated_items = extract_json(response)
    if new_curated_items:
        curated_items = new_curated_items
        response += beautify_curated_items(curated_items)
        image_generation_response = "A room with " + \
                                    ", ".join([i["item_name"] for i in curated_items])
        print(image_generation_response)
    return response

# Function for prompt handling
def prompt(text, history, language):
    Language = 'EN-US'
    text1 = translator.translate_text(text, target_lang=Language)
    text_1 = text1.text
    bot_response = chat(text_1)
    Language = language
    text2 = translator.translate_text(bot_response, target_lang=Language)
    text_2 = text2.text
    history = history + [(text, text_2)]
    return gr.update(value=""), history

# Gradio UI setup
with gr.Blocks() as demo:
    gr.Markdown("# Hepsiburada - AI Shopping Assistant")
    with gr.Row():
        with gr.Column():
            chatbot = gr.Chatbot([], elem_id="chatbot")
            txt_language = gr.Dropdown(
                label="language",
                choices=[
                    "EN-US",
                    "TR",
                ],
                allow_custom_value=True,
                value="TR",
                container=True,
            )
            msg = gr.Textbox(placeholder="Type your message here...")
            clear = gr.Button("Clear")
            msg.submit(prompt, [msg, chatbot, txt_language], [msg, chatbot])
            clear.click(lambda: None, None, chatbot, queue=False)

# Launch the Gradio UI
demo.launch(debug=True)