#!/usr/bin/env python3
"""
Test script for Gemini-powered flight scheduling chatbot
"""

import os
import sys
sys.path.append('flight_scheduler')

from llm_chatbot import LLMSchedulerBot

def main():
    print("🛩️ Flight Scheduling Chatbot (Gemini-powered)")
    print("=" * 50)
    
    # Initialize chatbot
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("❌ Please set GEMINI_API_KEY environment variable")
        print("   Get your API key from: https://makersuite.google.com/app/apikey")
        return
    
    bot = LLMSchedulerBot(api_key=api_key)
    
    print("✅ Chatbot initialized successfully!")
    print("\n💡 Try these example commands:")
    print("   • 'Crew C02 is sick'")
    print("   • 'Aircraft A101 needs maintenance in 3 hours'")
    print("   • 'Show me the schedule'")
    print("   • 'What's the current status?'")
    print("\n" + "=" * 50)
    
    # Interactive chat loop
    while True:
        try:
            user_input = input("\n🤖 You: ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'bye']:
                print("👋 Goodbye!")
                break
            
            if not user_input:
                continue
            
            print("\n🔄 Processing...")
            response = bot.chat(user_input)
            print(f"\n📋 Assistant: {response}")
            
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    main() 