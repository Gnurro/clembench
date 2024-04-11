"""
    Backend using llama.cpp for GGUF/GGML models.
"""

from typing import List, Dict, Tuple, Any, Union
import backends

# import torch

import llama_cpp
from llama_cpp import Llama

logger = backends.get_logger(__name__)


def load_model(model_spec: backends.ModelSpec) -> Any:
    """
    Load GGUF/GGML model weights from HuggingFace, into VRAM if available. Weights are distributed over all available
    GPUs for maximum speed - make sure to limit the available GPUs using environment variables if only a subset is to be
    used.
    :param model_spec: The ModelSpec for the model.
    :return: The llama_cpp model class instance of the loaded model.
    """
    logger.info(f'Start loading llama.cpp model weights from HuggingFace: {model_spec.model_name}')

    hf_repo_id = model_spec['huggingface_id']
    hf_model_file = model_spec['filename']

    # TODO: GPU offload on multiple GPUs

    if 'requires_api_key' in model_spec and model_spec['requires_api_key']:
        # load HF API key:
        creds = backends.load_credentials("huggingface")
        api_key = creds["huggingface"]["api_key"]
        # load model using its default configuration:
        # model = Llama.from_pretrained(hf_repo_id, hf_model_file, token=api_key, device_map="auto", torch_dtype="auto")
        # model = Llama.from_pretrained(hf_repo_id, hf_model_file, token=api_key)
        model = Llama.from_pretrained(hf_repo_id, hf_model_file, token=api_key, verbose=False)
    else:
        model = Llama.from_pretrained(hf_repo_id, hf_model_file, verbose=False)
        # model = Llama.from_pretrained(hf_repo_id, hf_model_file)
        # model = Llama.from_pretrained(hf_repo_id, hf_model_file, n_gpu_layers=-1)  # offloads all layers to GPU

    logger.info(f"Finished loading llama.cpp model: {model_spec.model_name}")
    # logger.info(f"Model device map: {model.hf_device_map}")

    return model


class LlamaCPPLocal(backends.Backend):
    """
    Model/backend handler class for locally-run GGUF/GGML models.
    """
    def __init__(self):
        super().__init__()

    def get_model_for(self, model_spec: backends.ModelSpec) -> backends.Model:
        """
        Get a LlamaCPPLocalModel instance with the passed model and settings. Will load all required data for using
        the model upon initialization.
        :param model_spec: The ModelSpec for the model.
        :return: The Model class instance of the model.
        """
        # torch.set_num_threads(1)
        return LlamaCPPLocalModel(model_spec)


class LlamaCPPLocalModel(backends.Model):
    """
    Class for loaded models ready for generation.
    """
    def __init__(self, model_spec: backends.ModelSpec):
        super().__init__(model_spec)
        # fail-fast
        # self.tokenizer, self.config, self.context_size = load_config_and_tokenizer(model_spec)
        self.model = load_model(model_spec)

        # get context size from model metadata:
        for key, value in self.model.metadata.items():
            # print(key, value)
            if "context_length" in key:
                self.context_size = value

        # placeholders for BOS/EOS:
        self.bos_string = None
        self.eos_string = None

        # check chat template:
        if model_spec.premade_chat_template:
            # jinja chat template available in metadata
            self.chat_template = self.model.metadata['tokenizer.chat_template']
        else:
            self.chat_template = model_spec.custom_chat_template

        if hasattr(self.model, 'chat_handler'):
            if not self.model.chat_handler:
                # no custom chat handler
                pass
            else:
                print("custom chat handler:", self.model.chat_handler)
                # TODO: check for custom chat handlers and how to get the template from them

        if hasattr(self.model, 'chat_format'):
            if not self.model.chat_format:
                # no guessed chat format
                pass
            else:
                if self.model.chat_format == "chatml":
                    # get BOS/EOS strings for chatml from llama.cpp:
                    self.bos_string = llama_cpp.llama_chat_format.CHATML_BOS_TOKEN
                    self.eos_string = llama_cpp.llama_chat_format.CHATML_BOS_TOKEN
                elif self.model.chat_format == "mistral-instruct":
                    # get BOS/EOS strings for mistral-instruct from llama.cpp:
                    self.bos_string = llama_cpp.llama_chat_format.MISTRAL_INSTRUCT_BOS_TOKEN
                    self.eos_string = llama_cpp.llama_chat_format.MISTRAL_INSTRUCT_EOS_TOKEN

        # for key, value in self.model.__dict__.items():
        #    print(key, value)

        # print(self.model.context_params.__dict__)
        # print(self.model._ctx.__dict__)
        # print(self.model._ctx.params.__dict__)
        # print(self.model.model_params.__dict__)

        # TODO: check how to get eos/bos AS STR for templates that require them (set in registry for now...)

        # tokenized_chatml_bos = self.model.tokenize(b"<s>", add_bos=False)
        tokenized_chatml_bos = self.model.tokenize(b' you', add_bos=False)
        # print(tokenized_chatml_bos)
        # print(self.model.detokenize(tokenized_chatml_bos))

        # bos_id = int(self.model.metadata['tokenizer.ggml.bos_token_id'])
        # print(bos_id)

        # bos_str = self.model.detokenize([bos_id])
        # bos_str = self.model.detokenize([151643])
        # bos_str = self.model.detokenize([1])
        bos_str = self.model.detokenize([498])
        # bos_str = self.model.detokenize([151645])
        # bos_str = self.model.detokenize([148848])
        # bos_str = self.model.detokenize([148848]).decode("utf-8")
        # bos_str = self.model.detokenize([151643]).decode("utf-8")
        # bos_str = self.model.detokenize([151645]).decode("utf-8", errors='strict')
        # print("bos str:", bos_str)
        """"""
        # print(llama_cpp.llama_token_bos(self.model))

        # get BOS/EOS strings for template from registry:
        if not self.bos_string:
            self.bos_string = model_spec.bos_string
        if not self.eos_string:
            self.eos_string = model_spec.eos_string

        # init llama.cpp jinja chat formatter:
        self.chat_formatter = llama_cpp.llama_chat_format.Jinja2ChatFormatter(
            template=self.chat_template,
            bos_token=self.bos_string,
            eos_token=self.eos_string
        )

    def generate_response(self, messages: List[Dict],
                          return_full_text: bool = False,
                          log_messages: bool = False) -> Tuple[Any, Any, str]:
        """
        :param messages: for example
                [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Who won the world series in 2020?"},
                    {"role": "assistant", "content": "The Los Angeles Dodgers won the World Series in 2020."},
                    {"role": "user", "content": "Where was it played?"}
                ]
        :param return_full_text: If True, whole input context is returned.
        :param log_messages: If True, raw and cleaned messages passed will be logged.
        :return: the continuation
        """
        # log current given messages list:
        # if log_messages:
        #    logger.info(f"Raw messages passed: {messages}")

        # current_messages = _clean_messages(messages)
        current_messages = messages

        # log current flattened messages list:
        if log_messages:
            logger.info(f"Flattened messages: {current_messages}")

        # use llama.cpp jinja to apply chat template for prompt:
        prompt_text = self.chat_formatter(messages=current_messages).prompt

        prompt = {"inputs": prompt_text, "max_new_tokens": self.get_max_tokens(),
                  "temperature": self.get_temperature(), "return_full_text": return_full_text}

        # TODO: context size checking/setting for generation

        """
        # check context limit:
        context_check = _check_context_limit(self.context_size, prompt_tokens[0],
                                             max_new_tokens=self.get_max_tokens())
        if not context_check[0]:  # if context is exceeded, context_check[0] is False
            logger.info(f"Context token limit for {self.model_spec.model_name} exceeded: "
                        f"{context_check[1]}/{context_check[3]}")
            # fail gracefully:
            raise backends.ContextExceededError(f"Context token limit for {self.model_spec.model_name} exceeded",
                                                tokens_used=context_check[1], tokens_left=context_check[2],
                                                context_size=context_check[3])
        """

        # TODO: check sampling params and set them to neutral values

        model_output = self.model.create_chat_completion(
            current_messages,
            temperature=self.get_temperature(),
            max_tokens=self.get_max_tokens()
        )

        response = {'response': model_output}
        
        # cull input context:
        if not return_full_text:
            response_text = model_output['choices'][0]['message']['content'].strip()

            if 'output_split_prefix' in self.model_spec:
                response_text = response_text.rsplit(self.model_spec['output_split_prefix'], maxsplit=1)[1]

            eos_len = len(self.model_spec['eos_to_cull'])

            if response_text.endswith(self.model_spec['eos_to_cull']):
                response_text = response_text[:-eos_len]

        else:
            response_text = prompt_text + model_output['choices'][0]['message']['content'].strip()

        return prompt, response, response_text