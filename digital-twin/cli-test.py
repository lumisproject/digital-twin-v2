import os
import sys
import re
from dotenv import load_dotenv
from src.agent import LumisAgent
from src.ingestor import ingest_repo

# Load environment variables
load_dotenv()

def main():
    print("🚀 Starting Lumis Adaptive Digital Twin...")
    
    # Configuration from .env
    PROJECT_ID = os.getenv("DEFAULT_PROJECT_ID", "your-project-uuid-here") 
    REPO_URL = os.getenv("REPO_URL", "https://github.com/racemdammak/demo-repo")
    USER_ID = "cli-test-user"

    if not REPO_URL:
        print("⚠️ REPO_URL not found in .env. Please set it to test ingestion.")

    while True:
        print("\n--- LUMIS ADAPTIVE MENU ---")
        print("1. Ingest Repository (Build Knowledge Graph + Hybrid Index)")
        print("2. Chat with Agent (Adaptive Context Mode)")
        print("3. Exit")
        
        choice = input("Select an option: ").strip()
        
        if choice == "1":
            if not REPO_URL:
                print("❌ Cannot ingest: REPO_URL is missing in .env")
                continue
                
            print(f"\n🔄 Starting Ingestion for {REPO_URL}...")
            
            def progress_logger(task, msg):
                print(f"[{task}] {msg}")
                
            try:
                ingest_repo(REPO_URL, PROJECT_ID, USER_ID, progress_callback=progress_logger)
                print("\n✅ Ingestion Complete! Hybrid Indexing is active.")
            except Exception as e:
                print(f"\n❌ Ingestion Failed: {e}")
            
        elif choice == "2":
            print("\n💬 Configure Chat Session")
            print("1. Multi-Turn (Remembers context)")
            print("2. Single-Turn (Stateless)")
            
            mode_choice = input("Select Mode (default 1): ").strip()
            selected_mode = "single-turn" if mode_choice == "2" else "multi-turn"
            print(f">> Mode set to {selected_mode.upper()}")
            
            try:
                # Initialize the refactored Agent
                agent = LumisAgent(project_id=PROJECT_ID, mode=selected_mode)
                
                while True:
                    query = input("\nYou: ").strip()
                    if query.lower() in ["exit", "quit", "back"]:
                        break
                    
                    if not query:
                        continue
                        
                    # The ask() method now runs the internal investigation loop
                    # It will print '🤔 Step' and '🔹 Augmented Query' internally
                    response = agent.ask(query)
                    
                    print(f"\nLumis: {response}")
                    
            except Exception as e:
                print(f"\n❌ Error initializing agent: {e}")
                print("Ensure you ran the SQL migration for 'match_code_hybrid' first.")

        elif choice == "3":
            print("Goodbye!")
            sys.exit(0)

if __name__ == "__main__":
    main()