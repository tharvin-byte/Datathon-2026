import os
import requests
import json
import logging

logger = logging.getLogger(__name__)

class OpenRouterResponse:
    """A wrapper mimicking the structure of google-generativeai response object."""
    def __init__(self, text):
        self.text = text

class OpenRouterModel:
    """A wrapper implementing generate_content for OpenRouter API requests."""
    def __init__(self, model_name, api_key, system_instruction=None):
        # We target a reliable, high-performance model on OpenRouter.
        # Since 'gemini-3.1-flash-lite' isn't standard, we map it to 'google/gemini-2.5-flash'.
        self.model_name = "google/gemini-2.5-flash"
        self.api_key = api_key
        self.system_instruction = system_instruction

    def generate_content(self, prompt, **kwargs):
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8080",
            "X-Title": "KSP Crime AI Platform"
        }
        
        messages = []
        if self.system_instruction:
            messages.append({"role": "system", "content": self.system_instruction})
        messages.append({"role": "user", "content": prompt})

        # Safeguard: limit max_tokens to prevent 402 Payment Required for users
        # with low credit balances, because OpenRouter otherwise requests/reserves 65k tokens.
        max_tokens = 2000
        
        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens
        }

        logger.info(f"[OpenRouterModel] Invoking {self.model_name}...")
        response = requests.post(url, headers=headers, json=payload)
        
        # If we hit 402 Payment Required, or a credit-related bad request (some models might throw 400),
        # automatically fallback to openrouter/free router.
        if response.status_code == 402 or (response.status_code == 400 and "credit" in response.text.lower()):
            logger.warning(f"[OpenRouterModel] Credit limit hit. Retrying with openrouter/free fallback...")
            payload["model"] = "openrouter/free"
            response = requests.post(url, headers=headers, json=payload)

        if response.status_code != 200:
            logger.error(f"[OpenRouterModel] Error response {response.status_code}: {response.text}")
            raise Exception(f"OpenRouter API returned error {response.status_code}: {response.text}")

        res_json = response.json()
        try:
            choice = res_json["choices"][0]
            text = choice["message"]["content"]
            return OpenRouterResponse(text)
        except (KeyError, IndexError) as e:
            logger.error(f"[OpenRouterModel] Failed parsing response: {res_json}")
            raise Exception(f"Failed to parse OpenRouter response format: {e}")

def get_generative_model(model_name: str, system_instruction: str = None, api_key_env_var: str = "GEMINI_API_KEY"):
    """
    Factory function to instantiate either an OpenRouter client wrapper or
    native google-generativeai GenerativeModel based on the key prefix.
    """
    api_key = os.environ.get(api_key_env_var) or os.environ.get("GEMINI_API_KEY")
    
    if not api_key:
        raise ValueError(f"No API key found in environment for {api_key_env_var} or GEMINI_API_KEY")
        
    if api_key.startswith("sk-or-v1-"):
        logger.info(f"[LLMFactory] OpenRouter key detected. Creating OpenRouterModel for {model_name}...")
        return OpenRouterModel(model_name, api_key, system_instruction)
    else:
        logger.info(f"[LLMFactory] Standard Google key detected. Instantiating official SDK...")
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        
        # If the SDK version is old and doesn't support the requested name, use gemini-1.5-flash fallback
        try:
            return genai.GenerativeModel(model_name, system_instruction=system_instruction)
        except Exception:
            fallback_model = "gemini-1.5-flash"
            logger.warning(f"[LLMFactory] Failed creating {model_name}. Falling back to {fallback_model}...")
            return genai.GenerativeModel(fallback_model, system_instruction=system_instruction)
