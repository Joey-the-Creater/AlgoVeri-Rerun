from pathlib import Path
import sys
import argparse

from src.eval.verus_eval import VerusEval
from src.llm.providers import AnthropicProvider, GeminiProvider, OpenAICompatibleProvider, VLLMProvider

from src.eval.runner import Runner

def run_task(args):
    system_prompt = ""
    if args.model.startswith("gemini"):
        llm_provider = GeminiProvider()
    elif args.model.lower().split('/')[-1].startswith("qwen"):
        assert args.url, "url must be provided"
        llm_provider = VLLMProvider(endpoint=args.url)
    elif args.model.lower().split('/')[-1].startswith("devstral"):
        assert args.url, "url must be provided"
        llm_provider = VLLMProvider(endpoint=args.url)
        system_prompt = """You are Devstral-Medium-2-124B-Instruct-2512, a Large Language Model (LLM) created by Mistral AI, a French startup headquartered in Paris.
You power an AI assistant called Le Chat.
Your knowledge base was last updated on 2023-10-01.
The current date is {today}.

When you're not sure about some information or when the user's request requires up-to-date or specific data, you must use the available tools to fetch the information. Do not hesitate to use tools whenever they can provide a more accurate or complete response. If no relevant tools are available, then clearly state that you don't have the information and avoid making up anything.
If the user's question is not clear, ambiguous, or does not provide enough context for you to accurately answer the question, you do not try to answer it right away and you rather ask the user to clarify their request (e.g. "What are some good restaurants around me?" => "Where are you?" or "When is the next flight to Tokyo" => "Where do you travel from?").
You are always very attentive to dates, in particular you try to resolve dates (e.g. "yesterday" is {yesterday}) and when asked about information at specific dates, you discard information that is at another date.
You follow these instructions in all languages, and always respond to the user in the language they use or request.
Next sections describe the capabilities that you have.

# WEB BROWSING INSTRUCTIONS

You cannot perform any web search or access internet to open URLs, links etc. If it seems like the user is expecting you to do so, you clarify the situation and ask the user to copy paste the text directly in the chat.

# MULTI-MODAL INSTRUCTIONS

You have the ability to read images, but you cannot generate images. You also cannot read nor transcribe audio files or videos.

# TOOL CALLING INSTRUCTIONS

You may have access to tools that you can use to fetch information or perform actions. You must use these tools in the following situations:

1. When the request requires up-to-date information.
2. When the request requires specific data that you do not have in your knowledge base.
3. When the request involves actions that you cannot perform without tools.

Always prioritize using tools to provide the most accurate and helpful response. If tools are not available, inform the user that you cannot perform the requested action at the moment."""
    elif args.model.lower().split('/')[-1].startswith("gpt-oss"):
        assert args.url, "url must be provided"
        llm_provider = VLLMProvider(endpoint=args.url)
    elif args.model.lower().split('/')[-1].startswith(("gpt-5", "gpt-4")):
        if args.model.lower().split('/')[-1].startswith("gpt-5.5") and args.reasoning_effort == "max":
            raise ValueError("GPT-5.5 supports reasoning effort through xhigh, not max")
        llm_provider = OpenAICompatibleProvider(
            reasoning_effort=args.reasoning_effort,
            max_output_tokens=args.max_output_tokens,
        )
    elif args.model.lower().split('/')[-1].startswith("claude-"):
        if args.reasoning_effort == "none":
            raise ValueError("Claude Opus 5 does not support reasoning effort 'none'")
        llm_provider = AnthropicProvider(
            reasoning_effort=args.reasoning_effort,
            max_output_tokens=args.max_output_tokens,
            thinking_mode=args.anthropic_thinking,
        )
    else:
        raise ValueError(f"Unknown model {args.model}")
    
    cfg_path = Path(args.cfg_path)
    
    results_dir = Path(args.results_root) / args.language
    runner = Runner(
        llm_provider=llm_provider,
        language=args.language,
        cfg_path=str(cfg_path),
        results_root=str(results_dir),
    )

    # If stdin is piped, use that as the problem directory; otherwise use the default path.
    default_dir = "algoveri_data/stack_push"
    problem_dir = args.problem_dir or default_dir
    try:
        if not args.problem_dir and not sys.stdin.isatty():
            piped = sys.stdin.read().strip()
            if piped:
                problem_dir = piped
    except Exception:
        # fallback to default
        problem_dir = default_dir

    res = runner.run_problem(
        problem_dir=str(problem_dir),
        max_rounds=args.max_rounds,
        num_passes=args.num_passes,
        model=args.model,
        system_prompt=system_prompt,
        debug=args.debug,
    )
    print(res)


if __name__ == "__main__":
    argparser = argparse.ArgumentParser()
    argparser.add_argument("--model", type=str, default="gemini-3-flash-preview")
    argparser.add_argument("--max_rounds", type=int, default=15)
    argparser.add_argument("--num_passes", type=int, default=1)
    argparser.add_argument(
        "--reasoning_effort",
        choices=("none", "low", "medium", "high", "xhigh", "max"),
        default="medium",
    )
    argparser.add_argument("--debug", action="store_true")
    argparser.add_argument("--cfg_path", type=str, default="test/config_test.yaml")
    argparser.add_argument("--results_root", type=str, default="test_results_scale")
    argparser.add_argument("--problem_dir", type=str, default="")
    argparser.add_argument("--language", type=str, default="verus")
    argparser.add_argument("--url", type=str, default="")
    argparser.add_argument("--max_output_tokens", type=int, default=32768)
    argparser.add_argument(
        "--anthropic_thinking",
        choices=("adaptive", "disabled"),
        default=None,
        help="Claude thinking mode; defaults to ANTHROPIC_THINKING or adaptive",
    )
    args = argparser.parse_args()
    run_task(args)
