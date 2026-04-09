import sys
import os


def save_rule(content, filename):
    # Ensure the rules directory exists
    rules_path = os.path.join(".agents", "rules")
    if not os.path.exists(rules_path):
        os.makedirs(rules_path)

    # Clean the filename
    if not filename.endswith(".md"):
        filename += ".md"

    full_path = os.path.join(rules_path, filename)

    # Write the rule
    with open(full_path, "w") as f:
        f.write(f"# Rule: {filename.replace('.md', '').title()}\n")
        f.write(content)

    print(f"Successfully learned: {full_path}")


if __name__ == "__main__":
    # Antigravity passes arguments via CLI
    if len(sys.argv) > 2:
        save_rule(sys.argv[1], sys.argv[2])
