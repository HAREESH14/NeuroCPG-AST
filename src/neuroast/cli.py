"""
NeuroAST CLI — Command-line interface for structural verification.

Provides three commands:
    neuroast verify    — Full pipeline (translate + verify + repair)
    neuroast extract   — Show structural fingerprint of a source file
    neuroast compare   — Compare structures of a C file and a Java file
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from neuroast.core.config import NeuroASTSettings
from neuroast.core.pipeline import VerificationPipeline
from neuroast.symbolic.extractor import StructuralExtractor
from neuroast.verification.matcher import TreeSitterVerifier
from neuroast.verification.structures import ControlFlowNode

app = typer.Typer(
    name="neuroast",
    help="NeuroAST: Neuro-Symbolic Code Translation Verifier",
    add_completion=False,
)
console = Console()


@app.command()
def verify(
    source: Annotated[Path, typer.Argument(help="Path to the C source file")],
    model: Annotated[
        str, typer.Option("--model", "-m", help="LLM model identifier")
    ] = "groq/llama-3.3-70b-versatile",
    max_retries: Annotated[
        int, typer.Option("--max-retries", "-r", help="Max repair iterations")
    ] = 3,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Save result JSON to file")
    ] = None,
) -> None:
    """Translate a C file to Java with neuro-symbolic verification."""
    if not source.exists():
        console.print(f"[red]Error:[/red] File not found: {source}")
        raise typer.Exit(1)

    c_source = source.read_text()

    settings = NeuroASTSettings(
        model=model,
        max_retries=max_retries,
    )
    pipeline = VerificationPipeline(settings=settings)

    console.print(
        Panel(
            f"[bold]Source:[/bold] {source}\n"
            f"[bold]Model:[/bold] {model}\n"
            f"[bold]Max retries:[/bold] {max_retries}",
            title="🧠 NeuroAST Verify",
        )
    )

    result = asyncio.run(pipeline.run(c_source))

    # Display result.
    if result.success:
        conf = result.final_confidence
        console.print(f"\n[bold green]✅ Verified![/bold green] Confidence: {conf:.2f}")
        console.print(f"   Attempts: {result.attempts}")
    else:
        console.print(f"\n[bold red]❌ Failed[/bold red] after {result.attempts} attempts")
        console.print(f"   Final confidence: {result.final_confidence:.2f}")
        console.print(f"   Hallucinations found: {result.total_hallucinations_found}")

    # Show Java output.
    console.print("\n[bold]Generated Java:[/bold]")
    console.print(result.java_code)

    # Save to file if requested.
    if output:
        output.write_text(result.model_dump_json(indent=2))
        console.print(f"\n[dim]Result saved to {output}[/dim]")


@app.command()
def extract(
    source: Annotated[Path, typer.Argument(help="Path to a source file (C or Java)")],
    language: Annotated[
        str, typer.Option("--language", "-l", help="Language: 'c' or 'java'")
    ] = "c",
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Extract and display the structural fingerprint of a source file."""
    if not source.exists():
        console.print(f"[red]Error:[/red] File not found: {source}")
        raise typer.Exit(1)

    if language not in ("c", "java"):
        console.print(f"[red]Error:[/red] Language must be 'c' or 'java', got '{language}'")
        raise typer.Exit(1)

    code = source.read_text()
    extractor = StructuralExtractor(language)  # type: ignore[arg-type]
    cfg = extractor.extract(code)

    if output_json:
        print(cfg.model_dump_json(indent=2))
        return

    # Pretty-print the CFG.
    console.print(
        Panel(
            f"[bold]File:[/bold] {source}\n"
            f"[bold]Language:[/bold] {language}\n"
            f"[bold]Functions:[/bold] {len(cfg.functions)}\n"
            f"[bold]Total elements:[/bold] {cfg.total_elements}",
            title="🌳 Structural Fingerprint",
        )
    )

    # Summary table.
    table = Table(title="Element Counts")
    table.add_column("Type", style="cyan")
    table.add_column("Count", style="green", justify="right")

    for node_type, count in sorted(cfg.summary().items()):
        table.add_row(node_type, str(count))

    console.print(table)

    # Show function details.
    for func in cfg.functions:
        console.print(f"\n[bold]{func.name}[/bold] (line {func.line}, depth {func.depth}):")
        _print_tree(func, indent=2)


@app.command()
def compare(
    source: Annotated[Path, typer.Argument(help="Path to the C source file")],
    target: Annotated[Path, typer.Argument(help="Path to the Java target file")],
    threshold: Annotated[
        float, typer.Option("--threshold", "-t", help="Confidence threshold")
    ] = 0.95,
) -> None:
    """Compare the structural fingerprints of a C file and a Java file."""
    if not source.exists() or not target.exists():
        console.print("[red]Error:[/red] One or both files not found")
        raise typer.Exit(1)

    c_source = source.read_text()
    java_target = target.read_text()

    verifier = TreeSitterVerifier(confidence_threshold=threshold)
    report = verifier.verify(c_source, java_target)

    # Display result.
    if report.is_aligned:
        console.print(f"[bold green]✅ Aligned[/bold green] (confidence: {report.confidence:.2f})")
    else:
        console.print(f"[bold red]❌ Misaligned[/bold red] (confidence: {report.confidence:.2f})")
        console.print(f"\n[bold]Hallucinations ({len(report.hallucinations)}):[/bold]")
        for i, h in enumerate(report.hallucinations, 1):
            console.print(f"  {i}. [{h.category.upper()}] {h.node_type} — {h.description}")

    # Summary table.
    table = Table(title="Structural Comparison")
    table.add_column("Type", style="cyan")
    table.add_column("Source", style="green", justify="right")
    table.add_column("Target", style="yellow", justify="right")
    table.add_column("Match", justify="center")

    all_types = sorted(set(report.source_summary.keys()) | set(report.target_summary.keys()))
    for t in all_types:
        s = report.source_summary.get(t, 0)
        tgt = report.target_summary.get(t, 0)
        match = "✅" if s == tgt else "❌"
        table.add_row(t, str(s), str(tgt), match)

    console.print(table)


def _print_tree(node: ControlFlowNode, indent: int = 0) -> None:
    """Recursively print a ControlFlowNode tree."""
    prefix = " " * indent
    label = node.node_type
    if node.name:
        label += f" ({node.name})"
    console.print(f"{prefix}├── {label}  [dim]line {node.line}[/dim]")
    for child in node.children:
        _print_tree(child, indent + 4)


if __name__ == "__main__":
    app()
