from core.agent import CompassBot

def main():
    print("Select Language / 选择语言:")
    print("1: English")
    print("2: 中文")
    choice = input("Choice (1/2): ").strip()
    
    lang = "en" if choice == "1" else "cn"
    
    try:
        # Initialize the bot with selected language
        bot = CompassBot(lang=lang)
        
        # Start the State Machine Loop
        bot.run()
        
    except KeyboardInterrupt:
        if lang == "en":
            print("\nStopped by user.")
        else:
            print("\n脚本已停止。")
    except Exception as e:
        if lang == "en":
            print(f"\nAn error occurred: {e}")
        else:
            print(f"\n发生错误: {e}")

if __name__ == "__main__":
    main()
