import os
import logging
import json
import time
from typing import List, Dict, Any

import anthropic
from openai import OpenAI
from picklecachefunc import check_cache
import tqdm

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

@check_cache(arg_name="file_name", create_dirs=True)
def chatgpt(system_prompt, user_prompts, file_name, model_name="gpt-4.1"):
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


def create_batch_requests(system_prompt: str, user_prompts: List[str], model_name: str = "gpt-4.1") -> List[Dict[str, Any]]:
    """Create batch request objects for OpenAI batch API."""
    requests = []
    for i, user_prompt in enumerate(user_prompts):
        request = {
            "custom_id": f"request_{i}",
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            }
        }
        requests.append(request)
    return requests


def save_batch_file(requests: List[Dict[str, Any]], file_path: str) -> None:
    """Save batch requests to JSONL file."""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w') as f:
        for request in requests:
            f.write(json.dumps(request) + '\n')


def submit_batch_job(client: OpenAI, input_file_path: str, description: str = "Batch job") -> str:
    """Submit a batch job to OpenAI and return the batch ID."""
    logging.info(f"Uploading batch file: {input_file_path}")
    
    # Upload the file
    with open(input_file_path, 'rb') as f:
        batch_input_file = client.files.create(
            file=f,
            purpose="batch"
        )
    
    logging.info(f"File uploaded with ID: {batch_input_file.id}")
    
    # Create the batch job
    batch_job = client.batches.create(
        input_file_id=batch_input_file.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
        metadata={"description": description}
    )
    
    logging.info(f"Batch job created with ID: {batch_job.id}")
    return batch_job.id


def wait_for_batch_completion(client: OpenAI, batch_id: str, check_interval: int = 60) -> str:
    """Wait for batch job to complete and return the output file ID."""
    logging.info(f"Waiting for batch {batch_id} to complete...")
    
    while True:
        try:
            batch_status = client.batches.retrieve(batch_id)
            logging.info(f"Batch status: {batch_status.status}")
            
            # Log additional details
            if hasattr(batch_status, 'request_counts'):
                logging.info(f"Request counts: {batch_status.request_counts}")
            
            if batch_status.status == "completed":
                logging.info(f"Batch completed! Output file ID: {batch_status.output_file_id}")
                return batch_status.output_file_id
            elif batch_status.status in ["failed", "expired", "cancelled"]:
                # Get detailed error information
                error_details = {
                    "status": batch_status.status,
                    "errors": getattr(batch_status, 'errors', None),
                    "request_counts": getattr(batch_status, 'request_counts', None),
                    "metadata": getattr(batch_status, 'metadata', None),
                }
                logging.error(f"Batch job failed. Details: {error_details}")
                
                # If there's an error file, try to download it for more details
                if hasattr(batch_status, 'error_file_id') and batch_status.error_file_id:
                    try:
                        error_file_content = client.files.content(batch_status.error_file_id)
                        logging.error(f"Error file content: {error_file_content.content.decode('utf-8')}")
                    except Exception as e:
                        logging.error(f"Could not retrieve error file: {e}")
                
                raise Exception(f"Batch job failed with status: {batch_status.status}. Details: {error_details}")
            
            logging.info(f"Batch still processing. Checking again in {check_interval} seconds...")
            time.sleep(check_interval)
        except Exception as e:
            logging.error(f"Error checking batch status: {e}")
            raise


def download_batch_results(client: OpenAI, output_file_id: str, output_path: str) -> None:
    """Download batch results from OpenAI."""
    logging.info(f"Downloading batch results to: {output_path}")
    
    file_response = client.files.content(output_file_id)
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'wb') as f:
        f.write(file_response.content)
    
    logging.info("Batch results downloaded successfully")


def parse_batch_results(output_path: str) -> Dict[str, str]:
    """Parse batch results and return responses mapped by custom_id."""
    results = {}
    
    with open(output_path, 'r') as f:
        for line in f:
            result = json.loads(line.strip())
            custom_id = result["custom_id"]
            
            if result.get("response") and result["response"].get("body"):
                response_content = result["response"]["body"]["choices"][0]["message"]["content"]
                results[custom_id] = response_content
            else:
                logging.warning(f"No valid response for {custom_id}: {result}")
                results[custom_id] = None
    
    return results


@check_cache(arg_name="file_name", create_dirs=True)
def chatgpt_batch(system_prompt: str, user_prompts: List[str], file_name: str, model_name: str = "gpt-4.1", 
                  batch_description: str = "Paper relevance batch job") -> List[str]:
    """Process prompts using OpenAI batch API."""
    logging.info(f"Starting batch processing for {len(user_prompts)} prompts")
    
    # Validate inputs
    if not user_prompts:
        logging.error("No prompts provided for batch processing")
        return []
    
    if len(user_prompts) > 50000:  # OpenAI batch limit
        logging.error(f"Too many prompts: {len(user_prompts)}. Batch API supports max 50,000 requests.")
        raise ValueError(f"Too many prompts: {len(user_prompts)}. Batch API supports max 50,000 requests.")
    
    # Check for empty or extremely long prompts
    for i, prompt in enumerate(user_prompts):
        if not prompt.strip():
            logging.warning(f"Empty prompt at index {i}")
        if len(prompt) > 100000:  # Very long prompt warning
            logging.warning(f"Very long prompt at index {i}: {len(prompt)} characters")
    
    logging.info(f"Using model: {model_name}")
    
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    
    # Create batch directory based on file_name
    batch_dir = os.path.dirname(file_name).replace('.pkl', '_batch')
    os.makedirs(batch_dir, exist_ok=True)
    
    # File paths
    input_file_path = os.path.join(batch_dir, "batch_input.jsonl")
    output_file_path = os.path.join(batch_dir, "batch_output.jsonl")
    
    logging.info(f"Batch files will be saved to: {batch_dir}")
    
    # Create and save batch requests
    requests = create_batch_requests(system_prompt, user_prompts, model_name)
    logging.info(f"Created {len(requests)} batch requests")
    save_batch_file(requests, input_file_path)
    logging.info(f"Saved batch requests to: {input_file_path}")
    
    # Submit batch job
    batch_id = submit_batch_job(client, input_file_path, batch_description)
    
    # Wait for completion
    output_file_id = wait_for_batch_completion(client, batch_id)
    
    # Download results
    download_batch_results(client, output_file_id, output_file_path)
    
    # Parse results
    results = parse_batch_results(output_file_path)
    
    # Return responses in the same order as input prompts
    responses = []
    for i in range(len(user_prompts)):
        custom_id = f"request_{i}"
        if custom_id in results and results[custom_id] is not None:
            responses.append(results[custom_id])
        else:
            logging.error(f"Missing or invalid response for prompt {i}")
            responses.append("")  # Return empty string for failed requests
    
    logging.info(f"Batch processing completed. Processed {len(responses)} responses")
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
    model_name = "gpt-4.1"

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
