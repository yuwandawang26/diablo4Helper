from core.agent import CompassBot

def main():
    try:
        # Initialize the bot
        bot = CompassBot()
        
        # Start the State Machine Loop
        bot.run()
        
    except KeyboardInterrupt:
        print("\nStopped by user.")
    except Exception as e:
        print(f"\nAn error occurred: {e}")

if __name__ == "__main__":
    main()
