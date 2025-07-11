import google.generativeai as genai
import json
import os
from constraint_manager import ConstraintManager

class LLMSchedulerBot:
    def __init__(self, api_key=None):
        # Initialize Gemini client
        if api_key:
            genai.configure(api_key=api_key)
        else:
            # Try to get from environment variable
            api_key = os.getenv('GEMINI_API_KEY')
            if api_key:
                genai.configure(api_key=api_key)
            else:
                print("Warning: No Gemini API key provided. Set GEMINI_API_KEY environment variable or pass api_key parameter.")
                genai.configure(api_key=None)
        
        # Initialize constraint manager
        self.constraint_manager = ConstraintManager()
        
        # Conversation history
        self.conversation_history = []
        
        # Initialize Gemini model
        try:
            self.model = genai.GenerativeModel('gemini-2.5-flash')
        except Exception as e:
            print(f"Warning: Could not initialize Gemini model: {e}")
            self.model = None
    
    def chat(self, message):
        """Process a user message and return response"""
        if not self.model:
            return "Error: Gemini API key not configured. Please set GEMINI_API_KEY environment variable."
        
        # Add to conversation history
        self.conversation_history.append({"role": "user", "content": message})
        
        # Get LLM response
        llm_response = self._get_llm_response(message)
        
        # Execute action
        try:
            result = self._execute_action(llm_response)
            
            # Add response to history
            self.conversation_history.append({"role": "assistant", "content": result})
            
            return result
        except Exception as e:
            error_msg = f"Error processing request: {str(e)}"
            self.conversation_history.append({"role": "assistant", "content": error_msg})
            return error_msg
    
    def _get_llm_response(self, message):
        """Get structured response from LLM"""
        system_prompt = """You are a flight scheduling assistant. Parse user requests and respond with JSON only.

Available actions:
- crew_unavailable: Mark crew as unavailable
- maintenance_alert: Set aircraft maintenance due
- show_schedule: Display current schedule
- add_flight: Add a new flight
- remove_flight: Remove a flight

Respond with JSON in this exact format:
{
    "action": "crew_unavailable|maintenance_alert|show_schedule|add_flight|remove_flight",
    "crew_id": "C01" (if crew action),
    "aircraft_id": "A101" (if maintenance action),
    "hours": 2 (if maintenance action),
    "explanation": "Brief explanation of what you're doing"
}

Examples:
User: "Crew C02 is sick"
Response: {"action": "crew_unavailable", "crew_id": "C02", "explanation": "Marking crew C02 as unavailable due to illness"}

User: "Aircraft A101 needs maintenance in 3 hours"
Response: {"action": "maintenance_alert", "aircraft_id": "A101", "hours": 3, "explanation": "Setting A101 maintenance alert for 3 hours"}

User: "Show me the schedule"
Response: {"action": "show_schedule", "explanation": "Displaying current optimized schedule"}

IMPORTANT: Respond with ONLY valid JSON, no additional text or formatting."""

        try:
            # Create the full prompt
            full_prompt = f"{system_prompt}\n\nUser request: {message}\n\nJSON response:"
            
            # Generate response using Gemini
            response = self.model.generate_content(full_prompt)
            
            # Extract the response text
            content = response.text.strip()
            
            # Clean up the response - remove any markdown formatting if present
            if content.startswith('```json'):
                content = content[7:]
            if content.endswith('```'):
                content = content[:-3]
            content = content.strip()
            
            # Parse JSON response
            return json.loads(content)
            
        except json.JSONDecodeError as e:
            print(f"JSON parsing error: {e}")
            print(f"Raw response: {content}")
            # Fallback if LLM doesn't return valid JSON
            return self._fallback_parsing(message)
        except Exception as e:
            print(f"Gemini API error: {e}")
            return {"action": "error", "explanation": f"LLM error: {str(e)}"}
    
    def _fallback_parsing(self, message):
        """Simple fallback parsing if LLM fails"""
        message_lower = message.lower()
        
        if "crew" in message_lower and ("sick" in message_lower or "unavailable" in message_lower):
            # Extract crew ID
            import re
            crew_match = re.search(r'[C]\d+', message)
            if crew_match:
                crew_id = crew_match.group()
                return {
                    "action": "crew_unavailable",
                    "crew_id": crew_id,
                    "explanation": f"Marking crew {crew_id} as unavailable"
                }
        
        elif "maintenance" in message_lower:
            # Extract aircraft ID and hours
            import re
            aircraft_match = re.search(r'[A]\d+', message)
            hours_match = re.search(r'\d+', message)
            
            if aircraft_match and hours_match:
                aircraft_id = aircraft_match.group()
                hours = int(hours_match.group())
                return {
                    "action": "maintenance_alert",
                    "aircraft_id": aircraft_id,
                    "hours": hours,
                    "explanation": f"Setting {aircraft_id} maintenance alert for {hours} hours"
                }
        
        elif "schedule" in message_lower or "show" in message_lower:
            return {
                "action": "show_schedule",
                "explanation": "Displaying current schedule"
            }
        
        return {
            "action": "unknown",
            "explanation": "I didn't understand that request. Try: 'Crew C02 is sick' or 'Aircraft A101 needs maintenance in 3 hours'"
        }
    
    def _execute_action(self, action_data):
        """Execute the action specified by LLM"""
        action = action_data.get("action", "unknown")
        explanation = action_data.get("explanation", "")
        
        if action == "crew_unavailable":
            crew_id = action_data.get("crew_id")
            if crew_id:
                result = self.constraint_manager.update_crew_availability(crew_id, False)
                return self._format_crew_response(crew_id, result, explanation)
            else:
                return "Error: No crew ID specified"
        
        elif action == "maintenance_alert":
            aircraft_id = action_data.get("aircraft_id")
            hours = action_data.get("hours")
            if aircraft_id and hours is not None:
                result = self.constraint_manager.add_maintenance_alert(aircraft_id, hours)
                return self._format_maintenance_response(aircraft_id, hours, result, explanation)
            else:
                return "Error: No aircraft ID or hours specified"
        
        elif action == "show_schedule":
            result = self.constraint_manager.get_current_schedule()
            return self._format_schedule_response(result, explanation)
        
        elif action == "add_flight":
            # Future enhancement
            return "Add flight functionality not yet implemented"
        
        elif action == "remove_flight":
            # Future enhancement
            return "Remove flight functionality not yet implemented"
        
        elif action == "unknown":
            return explanation
        
        else:
            return f"Unknown action: {action}"
    
    def _format_crew_response(self, crew_id, result, explanation):
        """Format response for crew availability change"""
        response = f"✅ {explanation}\n\n"
        response += f"📊 Optimization Results:\n"
        response += f"- Objective Value: {result['objective_value']:.0f}\n"
        response += f"- Status: {'Optimal' if result['status'] == 2 else 'Infeasible'}\n\n"
        
        if result.get('changes'):
            response += "🔄 Changes Made:\n"
            for change in result['changes']:
                response += f"• {change}\n"
            response += "\n"
        
        response += "🛩️ Updated Schedule:\n"
        for flight in result['schedule'][:5]:  # Show first 5 flights
            response += f"• Flight {flight['flight_number']} ({flight['cargo_type']}): {flight['departure_time']} - Aircraft: {flight['aircraft']}, Crew: {flight['crew']}"
            if flight['delay'] > 0:
                response += f" (Delayed {flight['delay']} min)"
            response += "\n"
        
        if len(result['schedule']) > 5:
            response += f"... and {len(result['schedule']) - 5} more flights\n"
        
        return response
    
    def _format_maintenance_response(self, aircraft_id, hours, result, explanation):
        """Format response for maintenance alert"""
        response = f"🔧 {explanation}\n\n"
        response += f"📊 Optimization Results:\n"
        response += f"- Objective Value: {result['objective_value']:.0f}\n"
        response += f"- Status: {'Optimal' if result['status'] == 2 else 'Infeasible'}\n\n"
        
        if result.get('changes'):
            response += "🔄 Changes Made:\n"
            for change in result['changes']:
                response += f"• {change}\n"
            response += "\n"
        
        response += "🛩️ Updated Schedule:\n"
        for flight in result['schedule'][:5]:  # Show first 5 flights
            response += f"• Flight {flight['flight_number']} ({flight['cargo_type']}): {flight['departure_time']} - Aircraft: {flight['aircraft']}, Crew: {flight['crew']}"
            if flight['delay'] > 0:
                response += f" (Delayed {flight['delay']} min)"
            response += "\n"
        
        if len(result['schedule']) > 5:
            response += f"... and {len(result['schedule']) - 5} more flights\n"
        
        return response
    
    def _format_schedule_response(self, result, explanation):
        """Format response for schedule display"""
        response = f"📋 {explanation}\n\n"
        response += f"📊 Current Status:\n"
        response += f"- Objective Value: {result['objective_value']:.0f}\n\n"
        
        response += "🛩️ Current Schedule:\n"
        for flight in result['schedule']:
            response += f"• Flight {flight['flight_number']} ({flight['cargo_type']}, Priority {flight['priority']}): {flight['departure_time']} - Aircraft: {flight['aircraft']}, Crew: {flight['crew']}"
            if flight['delay'] > 0:
                response += f" (Delayed {flight['delay']} min)"
            response += "\n"
        
        return response
    
    def get_conversation_history(self):
        """Get conversation history"""
        return self.conversation_history
    
    def clear_history(self):
        """Clear conversation history"""
        self.conversation_history = [] 