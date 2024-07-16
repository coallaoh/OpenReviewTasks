import os
import json
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage

CHATBOTMODELS = {
    "GPT_4O": {
        "name": "gpt-4o",
        "pricing_input": 5. / 1000000,
        "pricing_output": 15. / 1000000
    },
    "GPT_3_5_TURBO": {
        "name": "gpt-3.5-turbo",
        "pricing_input": .5 / 1000000,
        "pricing_output": 1.5 / 1000000
    }
}


class ChatBot(object):
    def __init__(self, cache_root, openai_model, system_message):
        self.openai_model = openai_model
        self.cache_root = os.path.join(cache_root, self.openai_model["name"])
        os.makedirs(self.cache_root, exist_ok=True)
        self.chat = ChatOpenAI(
            temperature=.7,
            model_name=self.openai_model["name"],
            model_kwargs={"response_format": {"type": "json_object"}},
        )
        self.system_message = system_message

    def call_openai(self, human_message):
        response = self.chat([
            SystemMessage(content=self.system_message),
            HumanMessage(content=human_message),
        ])
        price = (response.usage_metadata["input_tokens"] * self.openai_model["pricing_input"] +
                 response.usage_metadata["output_tokens"] * self.openai_model["pricing_output"]) / 10
        try:
            content_json = json.loads(response.content)
        except Exception as e:
            print(f"Error checking item relevance: {e}")
            content_json = {}
        return content_json, price
