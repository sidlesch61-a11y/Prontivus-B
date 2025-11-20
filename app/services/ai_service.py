"""
AI Service
Handles integration with various AI providers (OpenAI, Google, Anthropic, Azure OpenAI)
"""

import asyncio
import time
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone
import json

# Provider imports
try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

try:
    import google.generativeai as genai
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False

from app.services.encryption_service import decrypt


class AIServiceError(Exception):
    """Custom exception for AI service errors"""
    pass


class AIService:
    """
    AI Service for interacting with various AI providers
    Supports: OpenAI, Google Gemini, Anthropic Claude, Azure OpenAI
    """
    
    def __init__(
        self,
        provider: str,
        api_key: str,
        model: str,
        base_url: Optional[str] = None,
        max_tokens: int = 2000,
        temperature: float = 0.7
    ):
        """
        Initialize AI Service
        
        Args:
            provider: AI provider ("openai", "google", "anthropic", "azure")
            api_key: API key for the provider (encrypted)
            model: Model name to use
            base_url: Custom base URL (for Azure OpenAI or custom endpoints)
            max_tokens: Maximum tokens to generate
            temperature: Temperature for generation (0.0-1.0)
        """
        self.provider = provider.lower()
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.max_tokens = max_tokens
        self.temperature = temperature
        
        # Decrypt API key if needed
        if self.api_key:
            decrypted_key = decrypt(self.api_key)
            if decrypted_key:
                self.api_key = decrypted_key
        
        # Initialize provider client
        self._client = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize the appropriate client based on provider"""
        if self.provider == "openai" or self.provider == "azure":
            if not OPENAI_AVAILABLE:
                raise AIServiceError("OpenAI library not installed. Install with: pip install openai")
            
            if self.provider == "azure":
                # Azure OpenAI
                if not self.base_url:
                    raise AIServiceError("base_url is required for Azure OpenAI")
                self._client = AsyncOpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    api_version="2024-02-15-preview"
                )
            else:
                # Standard OpenAI
                self._client = AsyncOpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url  # Can be None for standard OpenAI
                )
        
        elif self.provider == "anthropic":
            if not ANTHROPIC_AVAILABLE:
                raise AIServiceError("Anthropic library not installed. Install with: pip install anthropic")
            self._client = anthropic.AsyncAnthropic(api_key=self.api_key)
        
        elif self.provider == "google":
            if not GOOGLE_AVAILABLE:
                raise AIServiceError("Google Generative AI library not installed. Install with: pip install google-generativeai")
            genai.configure(api_key=self.api_key)
            # Store model name, will create model instance when needed
            self._model_name = self.model
            self._client = None  # Will be created per request
        
        else:
            raise AIServiceError(f"Unsupported provider: {self.provider}")
    
    async def test_connection(self) -> Dict[str, Any]:
        """
        Test connection to AI provider
        
        Returns:
            Dict with success status, message, and response time
        """
        start_time = time.time()
        
        try:
            test_prompt = "Hello, this is a connection test. Please respond with 'OK'."
            
            if self.provider == "openai" or self.provider == "azure":
                response = await self._client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": test_prompt}],
                    max_tokens=10,
                    temperature=0.0
                )
                result = response.choices[0].message.content
            
            elif self.provider == "anthropic":
                response = await self._client.messages.create(
                    model=self.model,
                    max_tokens=10,
                    temperature=0.0,
                    messages=[{"role": "user", "content": test_prompt}]
                )
                result = response.content[0].text
            
            elif self.provider == "google":
                # Google Generative AI is synchronous, run in executor
                loop = asyncio.get_event_loop()
                model = genai.GenerativeModel(self._model_name)
                response = await loop.run_in_executor(
                    None,
                    lambda: model.generate_content(
                        test_prompt,
                        generation_config=genai.types.GenerationConfig(
                            max_output_tokens=10,
                            temperature=0.0
                        )
                    )
                )
                result = response.text
            
            else:
                raise AIServiceError(f"Unsupported provider: {self.provider}")
            
            response_time_ms = int((time.time() - start_time) * 1000)
            
            return {
                "success": True,
                "message": "Connection test successful",
                "provider": self.provider,
                "model": self.model,
                "response_time_ms": response_time_ms,
                "test_response": result[:50]  # First 50 chars
            }
        
        except Exception as e:
            response_time_ms = int((time.time() - start_time) * 1000)
            return {
                "success": False,
                "message": f"Connection test failed: {str(e)}",
                "provider": self.provider,
                "model": self.model,
                "response_time_ms": response_time_ms,
                "error": str(e)
            }
    
    async def generate_completion(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        context: Optional[List[Dict[str, str]]] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Generate AI completion
        
        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            context: Optional conversation context (list of {"role": "user/assistant", "content": "..."})
        
        Returns:
            Tuple of (response_text, usage_stats)
            usage_stats contains: tokens_used, prompt_tokens, completion_tokens, response_time_ms
        """
        start_time = time.time()
        
        try:
            # Build messages
            messages = []
            
            if system_prompt:
                if self.provider == "anthropic":
                    # Anthropic uses system parameter separately
                    system_message = system_prompt
                else:
                    messages.append({"role": "system", "content": system_prompt})
            
            # Add context if provided
            if context:
                messages.extend(context)
            
            # Add current prompt
            messages.append({"role": "user", "content": prompt})
            
            # Generate response
            if self.provider == "openai" or self.provider == "azure":
                response = await self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature
                )
                
                result_text = response.choices[0].message.content
                usage = {
                    "tokens_used": response.usage.total_tokens,
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "response_time_ms": int((time.time() - start_time) * 1000)
                }
            
            elif self.provider == "anthropic":
                # Anthropic uses system parameter separately
                response = await self._client.messages.create(
                    model=self.model,
                    system=system_message if system_prompt else None,
                    messages=[m for m in messages if m["role"] != "system"],
                    max_tokens=self.max_tokens,
                    temperature=self.temperature
                )
                
                result_text = response.content[0].text
                usage = {
                    "tokens_used": response.usage.input_tokens + response.usage.output_tokens,
                    "prompt_tokens": response.usage.input_tokens,
                    "completion_tokens": response.usage.output_tokens,
                    "response_time_ms": int((time.time() - start_time) * 1000)
                }
            
            elif self.provider == "google":
                # Google Gemini
                full_prompt = prompt
                if system_prompt:
                    full_prompt = f"{system_prompt}\n\n{prompt}"
                
                # Google Generative AI is synchronous, run in executor
                loop = asyncio.get_event_loop()
                model = genai.GenerativeModel(self._model_name)
                response = await loop.run_in_executor(
                    None,
                    lambda: model.generate_content(
                        full_prompt,
                        generation_config=genai.types.GenerationConfig(
                            max_output_tokens=self.max_tokens,
                            temperature=self.temperature
                        )
                    )
                )
                
                result_text = response.text
                # Google doesn't provide detailed token usage in the same way
                # Estimate based on response length (rough approximation: 1 token ≈ 4 characters)
                estimated_tokens = len(full_prompt) // 4 + len(result_text) // 4
                usage = {
                    "tokens_used": estimated_tokens,
                    "prompt_tokens": len(full_prompt) // 4,
                    "completion_tokens": len(result_text) // 4,
                    "response_time_ms": int((time.time() - start_time) * 1000)
                }
            
            else:
                raise AIServiceError(f"Unsupported provider: {self.provider}")
            
            return result_text, usage
        
        except Exception as e:
            raise AIServiceError(f"AI generation failed: {str(e)}")
    
    async def analyze_clinical_data(
        self,
        clinical_data: Dict[str, Any],
        analysis_type: str = "general"
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Analyze clinical data using AI
        
        Args:
            clinical_data: Dictionary containing clinical information
            analysis_type: Type of analysis ("general", "diagnosis", "treatment", "risk")
        
        Returns:
            Tuple of (analysis_text, usage_stats)
        """
        # Build system prompt based on analysis type
        system_prompts = {
            "general": "You are a medical AI assistant. Analyze the provided clinical data and provide insights.",
            "diagnosis": "You are a medical AI assistant specialized in diagnosis. Analyze symptoms and clinical data to suggest possible diagnoses.",
            "treatment": "You are a medical AI assistant specialized in treatment recommendations. Analyze clinical data and suggest treatment options.",
            "risk": "You are a medical AI assistant specialized in risk assessment. Analyze clinical data and assess patient risk factors."
        }
        
        system_prompt = system_prompts.get(analysis_type, system_prompts["general"])
        
        # Format clinical data as prompt
        prompt = f"Analyze the following clinical data:\n\n{json.dumps(clinical_data, indent=2)}\n\nProvide a detailed analysis."
        
        return await self.generate_completion(prompt, system_prompt=system_prompt)
    
    async def suggest_diagnosis(
        self,
        symptoms: List[str],
        patient_history: Optional[Dict[str, Any]] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Suggest possible diagnoses based on symptoms
        
        Args:
            symptoms: List of symptoms
            patient_history: Optional patient history
        
        Returns:
            Tuple of (suggestions_list, usage_stats)
            suggestions_list contains: [{"diagnosis": "...", "confidence": "...", "reasoning": "..."}, ...]
        """
        system_prompt = "You are a medical AI assistant. Suggest possible diagnoses based on symptoms. Return your response as a JSON array of objects with 'diagnosis', 'confidence' (low/medium/high), and 'reasoning' fields."
        
        prompt = f"Symptoms: {', '.join(symptoms)}\n\n"
        if patient_history:
            prompt += f"Patient History: {json.dumps(patient_history, indent=2)}\n\n"
        prompt += "Suggest possible diagnoses with confidence levels and reasoning."
        
        response_text, usage = await self.generate_completion(prompt, system_prompt=system_prompt)
        
        # Try to parse JSON response
        try:
            # Extract JSON from response (might be wrapped in markdown code blocks)
            import re
            json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
            if json_match:
                suggestions = json.loads(json_match.group())
            else:
                suggestions = json.loads(response_text)
        except:
            # Fallback: create a simple suggestion from the text
            suggestions = [{
                "diagnosis": "See analysis",
                "confidence": "medium",
                "reasoning": response_text
            }]
        
        return suggestions, usage
    
    async def generate_treatment_suggestions(
        self,
        diagnosis: str,
        patient_data: Optional[Dict[str, Any]] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Generate treatment suggestions for a diagnosis
        
        Args:
            diagnosis: Diagnosis name
            patient_data: Optional patient data (allergies, medications, etc.)
        
        Returns:
            Tuple of (suggestions_list, usage_stats)
            suggestions_list contains: [{"treatment": "...", "type": "...", "notes": "..."}, ...]
        """
        system_prompt = "You are a medical AI assistant. Suggest treatment options for diagnoses. Return your response as a JSON array of objects with 'treatment', 'type' (medication/procedure/lifestyle), and 'notes' fields."
        
        prompt = f"Diagnosis: {diagnosis}\n\n"
        if patient_data:
            prompt += f"Patient Data: {json.dumps(patient_data, indent=2)}\n\n"
        prompt += "Suggest treatment options."
        
        response_text, usage = await self.generate_completion(prompt, system_prompt=system_prompt)
        
        # Try to parse JSON response
        try:
            import re
            json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
            if json_match:
                suggestions = json.loads(json_match.group())
            else:
                suggestions = json.loads(response_text)
        except:
            # Fallback: create a simple suggestion from the text
            suggestions = [{
                "treatment": "See analysis",
                "type": "general",
                "notes": response_text
            }]
        
        return suggestions, usage


def create_ai_service(
    provider: str,
    api_key_encrypted: str,
    model: str,
    base_url: Optional[str] = None,
    max_tokens: int = 2000,
    temperature: float = 0.7
) -> AIService:
    """
    Factory function to create an AI service instance
    
    Args:
        provider: AI provider name
        api_key_encrypted: Encrypted API key
        model: Model name
        base_url: Optional base URL
        max_tokens: Max tokens
        temperature: Temperature
    
    Returns:
        AIService instance
    """
    return AIService(
        provider=provider,
        api_key=api_key_encrypted,
        model=model,
        base_url=base_url,
        max_tokens=max_tokens,
        temperature=temperature
    )

