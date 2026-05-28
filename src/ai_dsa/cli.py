import click
import os
from dotenv import load_dotenv
from .database import Database
from .sandbox import Sandbox
from .sql_sandbox import SQLSandbox
from .providers import GeminiProvider, OllamaProvider, AnthropicProvider, OpenAIProvider
from .models import ProblemBank, SQLProblemBank

# Load environment variables
load_dotenv()

@click.group()
@click.pass_context
def main(ctx):
    """ai-dsa: Practice Data Structures and Algorithms in your terminal."""
    ctx.ensure_object(dict)
    
    # Paths
    base_dir = os.path.expanduser("~/.local/share/ai-dsa")
    db_path = os.path.join(base_dir, "dsa.db")
    
    # Problem dir: check current dir first, then fall back to package resource
    problems_dir = os.path.join(os.getcwd(), "data/problems")
    if not os.path.exists(problems_dir):
        # Fallback to a default location if needed
        pass
    
    os.makedirs(base_dir, exist_ok=True)
    
    # Initialize Core
    db = Database(db_path)
    bank = ProblemBank(problems_dir)
    sql_bank = SQLProblemBank(os.path.join(os.getcwd(), "data/sql"))
    
    # Sync file-based problems to DB
    bank.sync_to_db(db)
    sql_bank.sync_to_db(db)
    
    # DB Maintenance
    db.run_maintenance()
    
    ctx.obj['db'] = db
    ctx.obj['sandbox'] = Sandbox()
    ctx.obj['sql_sandbox'] = SQLSandbox()
    ctx.obj['bank'] = bank
    ctx.obj['sql_bank'] = sql_bank
    
    # AI Provider selection
    provider_type = os.getenv("AI_PROVIDER", "ollama").lower()
    model = os.getenv("AI_MODEL")
    
    if provider_type == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")
        ctx.obj['ai'] = GeminiProvider(api_key, model_name=model) if api_key else None
    elif provider_type == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY")
        ctx.obj['ai'] = AnthropicProvider(api_key, model_name=model) if api_key else None
    elif provider_type == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        ctx.obj['ai'] = OpenAIProvider(api_key, model_name=model) if api_key else None
    elif provider_type == "ollama":
        model = model or os.getenv("OLLAMA_MODEL", "llama3")
        ctx.obj['ai'] = OllamaProvider(model_name=model)
    else:
        ctx.obj['ai'] = None
@main.command()
@click.option('--topic', help='Filter problems by topic.')
@click.option('--id', 'problem_id', help='Start a specific problem by ID.')
@click.option('--dsa', is_flag=True, help='Start in DSA mode.')
@click.option('--sql', is_flag=True, help='Start in SQL mode.')
@click.option('--fix', is_flag=True, help='Start in FixSlop mode.')
@click.pass_context
def start(ctx, topic, problem_id, dsa, sql, fix):
    """Start a practice session."""
    from .tui import DSATUI
    bank = ctx.obj['bank']
    sql_bank = ctx.obj['sql_bank']
    problem = None
    mode = None

    if dsa: mode = "DSA"
    elif sql: mode = "SQL"
    elif fix: mode = "FixSlop"

    if problem_id:
        if mode == "SQL":
            problem = sql_bank.get_problem(problem_id)
        else:
            problem = bank.get_problem(problem_id)
    elif topic:
        if mode == "SQL":
            # Assuming SQL bank might need filter by topic too if added
            problem = sql_bank.problems[0] if sql_bank.problems else None
        else:
            problems = bank.filter_by_topic(topic)
            problem = problems[0] if problems else None

    # Launch TUI
    app = DSATUI()
    # Pass resources to app instance
    app.mode = mode or "DSA"
    app.mode_explicit = (mode is not None)
    app.problem = problem
    app.db = ctx.obj['db']
    app.bank = bank
    app.sql_bank = sql_bank
    app.ai = ctx.obj['ai']
    app.sandbox = ctx.obj['sandbox']
    app.sql_sandbox = ctx.obj['sql_sandbox']

    app.run()

@main.command()
@click.argument('file', type=click.Path(exists=True))
@click.option('--id', 'problem_id', required=True, help='Problem ID to test against.')
@click.pass_context
def submit(ctx, file, problem_id):
    """Submit a solution file for testing."""
    problem = ctx.obj['bank'].get_problem(problem_id)
    if not problem:
        click.echo(f"Problem {problem_id} not found.")
        return

    with open(file, 'r') as f:
        code = f.read()
    
    click.echo(f"Testing {problem.title}...")
    
    results = ctx.obj['sandbox'].run_test_cases(code, problem)
    
    all_passed = True
    for i, res in enumerate(results):
        status = "PASSED" if res['passed'] else "FAILED"
        click.echo(f"Test {i+1}: {status} ({res['runtime_ms']:.2f}ms)")
        if not res['passed']:
            all_passed = False
            if res['error']:
                click.echo(f"  Error: {res['error']}")

    ctx.obj['db'].add_submission(problem_id, problem.topic, code, all_passed, sum(r['runtime_ms'] for r in results))

@main.command()
@click.option('--topic', required=True, help='Topic for the problem.')
@click.option('--difficulty', default='Easy', help='Difficulty level.')
@click.pass_context
def generate(ctx, topic, difficulty):
    """Generate a new DSA problem using AI."""
    ai = ctx.obj['ai']
    if not ai:
        click.echo("AI not configured. Set AI_PROVIDER and API key in .env.")
        return

    click.echo(f"Generating a {difficulty} {topic} problem...")
    import asyncio
    try:
        problem_data = asyncio.run(ai.generate_problem(topic, difficulty))
        
        # Save to TOML
        import tomli_w
        problem_id = problem_data.get('id', topic.lower().replace(' ', '-') + '-' + difficulty.lower())
        file_path = f"data/problems/{problem_id}.toml"
        
        with open(file_path, 'wb') as f:
            tomli_w.dump(problem_data, f)
            
        click.echo(f"Problem generated and saved to {file_path}")
    except Exception as e:
        click.echo(f"Generation failed: {str(e)}")

@main.command()
@click.pass_context
def stats(ctx):
    """Show your progress and statistics."""
    stats_data = ctx.obj['db'].get_stats()
    if not stats_data:
        click.echo("No stats found. Start practicing!")
        return
    
    click.echo("--- DSA Progress ---")
    for row in stats_data:
        click.echo(f"{row['topic']}: {row['solved_count']} solved")

if __name__ == "__main__":
    main()
