from pathlib import Path
import sys
import argparse
import os
import json

from src.eval.verus_eval import VerusEval
from src.llm.providers import GeminiProvider, OpenAICompatibleProvider, VLLMProvider

from src.eval.semantic_eval import SemanticEval

def run_task(args):
    system_prompt = ""
    
    if args.model.lower().split('/')[-1].startswith("gpt-oss"):
        assert args.url, "url must be provided"
        llm_provider = VLLMProvider(endpoint=args.url)
    elif args.model.lower().split('/')[-1].startswith("gpt"):
        llm_provider = OpenAICompatibleProvider(reasoning_effort=args.reasoning_effort)
    else:
        raise ValueError(f"Unknown model {args.model}")
    
    eval = SemanticEval(llm_client=llm_provider, max_rounds=args.max_rounds)

    # If stdin is piped, use that as the problem directory; otherwise use the default path.
    default_dir = "algoveri_data/bubble_sort"
    problem_dir = args.problem_dir or default_dir
    try:
        if not args.problem_dir and not sys.stdin.isatty():
            piped = sys.stdin.read().strip()
            if piped:
                problem_dir = piped
    except Exception:
        # fallback to default
        problem_dir = default_dir

    task = problem_dir.split('/')[-1]

    friendly_test_model_name = args.testmodel.split('/')[-1]

    print(args.results_root)
    print(args.language)
    previous_result_file = os.path.join(args.results_root,args.language,f"{friendly_test_model_name}_{task}_{args.language}.json")
    print(previous_result_file)

    if not os.path.exists(previous_result_file):
        print(f"Result file {previous_result_file} does not exists. Skipping...")
        return
    previous_results = None
    with open(previous_result_file, 'r') as f:
        previous_results = json.load(f)
    if previous_results is None:
        return
    if isinstance(previous_results, dict) and previous_results.get("verified") is False:
        # it is unverified, do not need semantic check
        previous_results["parsed"] = False
        previous_results["verdict"] = False
        previous_results["analysis"] = ""
        new_results = previous_results
    elif isinstance(previous_results, dict) and previous_results.get("verified") is True:
        code = previous_results.get("details", {}).get("llm_response", {}).get("code", "")
        natural_language_file = os.path.join(problem_dir,f"{args.language}_nl.txt")
        with open(natural_language_file, 'r') as nf:
            natural_language = nf.read()
        sem_res = eval.run_single(natural_language=natural_language, formal_code=code, model=args.model, filename="", spec="", system_prompt=system_prompt, debug=args.debug)
        previous_results["parsed"] = sem_res.get("parsed", False)
        previous_results["verdict"] = sem_res.get("verdict", False)
        previous_results["analysis"] = sem_res.get("analysis", "")
        new_results = previous_results
    elif isinstance(previous_results, list):
        new_results = []
        for item in previous_results:
            if isinstance(item, dict) and item.get("verified") is True:
                code = item.get("details", {}).get("llm_response", {}).get("code", "")
                natural_language_file = os.path.join(problem_dir,f"{args.language}_nl.txt")
                with open(natural_language_file, 'r') as nf:
                    natural_language = nf.read()
                sem_res = eval.run_single(natural_language=natural_language, formal_code=code, model=args.model, filename="", spec="", system_prompt=system_prompt, debug=args.debug)
                item["parsed"] = sem_res.get("parsed", False)
                item["verdict"] = sem_res.get("verdict", False)
                item["analysis"] = sem_res.get("analysis", "")
            else:
                item["parsed"] = False
                item["verdict"] = False
                item["analysis"] = ""
            new_results.append(item)
    out_path = Path(args.save_root) / args.language / f"{friendly_test_model_name}_{task}_{args.language}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(new_results, indent=4))




if __name__ == "__main__":
    argparser = argparse.ArgumentParser()
    argparser.add_argument("--model", type=str, default="gpt-oss-120b")
    argparser.add_argument("--max_rounds", type=int, default=5)
    argparser.add_argument("--num_passes", type=int, default=1)
    argparser.add_argument(
        "--reasoning_effort",
        choices=("none", "low", "medium", "high", "xhigh", "max"),
        default="medium",
    )
    argparser.add_argument("--debug", action="store_true")
    argparser.add_argument("--cfg_path", type=str, default="algoveri/test/config_test.yaml")
    argparser.add_argument("--results_root", type=str, default="test_results")
    argparser.add_argument("--language", type=str, default="lean")
    argparser.add_argument("--testmodel", type=str, default="gpt-oss-120b")
    argparser.add_argument("--save_root", type=str, default="test_results_filter")
    argparser.add_argument("--problem_dir", type=str, default="")
    argparser.add_argument("--url", type=str, default="")
    args = argparser.parse_args()
    run_task(args)
