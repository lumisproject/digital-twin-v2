import os
import sys
from dotenv import load_dotenv
from src.agent import LumisAgent
from src.ingestor import ingest_repo

# Load environment variables
load_dotenv()

def main():
    print("🚀 Starting Lumis Digital Twin Backend...")
    
    # Configuration
    # Ideally, these come from your database or API request in a real platform.
    # For this CLI tool, we get them from ENV or use placeholders.
    PROJECT_ID = os.getenv("DEFAULT_PROJECT_ID", "your-project-uuid-here") 
    REPO_URL = os.getenv("REPO_URL", "https://github.com/racemdammak/demo-repo")
    USER_ID = "cli-user"

    while True:
        print("\n--- LUMIS MENU ---")
        print("1. Ingest Repository (Build Knowledge Graph)")
        print("2. Chat with Agent")
        print("3. Exit")
        
        choice = input("Select an option: ").strip()
        
        if choice == "1":
            print(f"\n🔄 Starting Ingestion for {REPO_URL}...")
            print(f"Project ID: {PROJECT_ID}")
            
            # Callback to print progress to console
            def progress_logger(task, msg):
                print(f"[{task}] {msg}")
                
            try:
                ingest_repo(REPO_URL, PROJECT_ID, USER_ID, progress_callback=progress_logger)
                print("\n✅ Ingestion Complete!")
            except Exception as e:
                print(f"\n❌ Ingestion Failed: {e}")
            
        elif choice == "2":
            print("\n💬 Configure Chat Session")
            print("1. Multi-Turn (Remembers context, good for conversation)")
            print("2. Single-Turn (Stateless, good for independent Q&A)")
            
            mode_choice = input("Select Mode (default 1): ").strip()
            
            # Map choice to mode string expected by LumisAgent
            if mode_choice == "2":
                selected_mode = "single-turn"
                print(">> Mode set to SINGLE-TURN")
            else:
                selected_mode = "multi-turn"
                print(">> Mode set to MULTI-TURN")
            
            try:
                # Initialize Agent with selected mode
                agent = LumisAgent(project_id=PROJECT_ID, mode=selected_mode)
                
                print(f"\n🟢 Agent Ready ({selected_mode}). Type 'exit' to return to menu.")
                
                while True:
                    query = input("\nYou: ")
                    if query.lower() in ["exit", "quit", "back"]:
                        break
                    
                    if not query.strip():
                        continue
                        
                    # Get response from Agent
                    response = agent.ask(query)
                    print(f"\nLumis: {response}")
                    
            except Exception as e:
                print(f"\n❌ Error initializing agent: {e}")
                print("Make sure you have ingested the repo first (Option 1).")

        elif choice == "3":
            print("Goodbye!")
            sys.exit(0)
            
        else:
            print("Invalid selection. Please try again.")

if __name__ == "__main__":
    main()