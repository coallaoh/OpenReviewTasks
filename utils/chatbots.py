import os
import logging

import anthropic
from openai import OpenAI
from picklecachefunc import check_cache
import tqdm

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

@check_cache(arg_name="file_name", create_dirs=True)
def chatgpt(system_prompt, user_prompts, file_name, model_name="gpt-4o"):
    logging.info("Starting chatgpt function")
    client = OpenAI(
        api_key=os.environ.get("OPENAI_API_KEY"),
    )

    responses = []

    for user_prompt in tqdm.tqdm(user_prompts):
        logging.debug(f"Sending prompt to chatgpt: {user_prompt}")
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                }
            ],
            model=model_name,
        )
        response = chat_completion.choices[0].message.content
        logging.debug(f"Received response from chatgpt: {response}")
        responses.append(response)
    logging.info("Completed chatgpt function")
    return responses


@check_cache(arg_name="file_name", create_dirs=True)
def claude(system_prompt, user_prompts, file_name, model_name="claude-3-5-sonnet-20240620"):
    logging.info("Starting claude function")
    client = anthropic.Anthropic()

    responses = []
    for user_prompt in tqdm.tqdm(user_prompts):
        logging.debug(f"Sending prompt to claude: {user_prompt}")
        message = client.messages.create(
            model=model_name,
            max_tokens=1000,
            temperature=0,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": user_prompt
                        }
                    ]
                }
            ]
        )
        response = message.content[0].text
        logging.debug(f"Received response from claude: {response}")
        responses.append(response)
    logging.info("Completed claude function")
    return responses

def test_chatgpt():
    logging.info("Testing chatgpt function")
    system_prompt = "You are an AI assistant."
    user_prompts = ["What is the capital of France?", "What is the largest mammal?"]
    file_name = "cache/test_chatgpt.pkl"
    model_name = "gpt-3.5-turbo"

    responses = chatgpt(system_prompt=system_prompt, user_prompts=user_prompts, file_name=file_name, model_name=model_name)
    
    assert len(responses) == 2
    assert "Paris" in responses[0]
    assert "blue whale" in responses[1].lower()
    logging.info("chatgpt function test passed")

def test_claude():
    logging.info("Testing claude function")
    system_prompt = "You are an AI assistant."
    user_prompts = ["What is the capital of Germany?", "What is the fastest land animal?"]
    file_name = "cache/test_claude.pkl"
    model_name = "claude-3-5-sonnet-20240620"

    responses = claude(system_prompt=system_prompt, user_prompts=user_prompts, file_name=file_name, model_name=model_name)
    
    assert len(responses) == 2
    assert "Berlin" in responses[0]
    assert "cheetah" in responses[1].lower()
    logging.info("claude function test passed")


if __name__ == "__main__":
    logging.info("Starting tests")
    test_chatgpt()
    test_claude()
    logging.info("All tests completed")
