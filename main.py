#!/usr/bin/env python3
"""
Wellness Reminder Application - Main Entry Point (Fixed Threading)
A background wellness reminder system for desk workers.
"""

import schedule
import time
import threading
import signal
import sys
from datetime import datetime, timedelta
import json
import logging
from pathlib import Path
import tkinter as tk
from queue import Queue
import random

from db import DatabaseManager
from notifier import NotificationManager
from utils import DateTimeUtils, DailyResetManager
from messages import MotivationalMessages

# Define the base directory of the script to make paths absolute
BASE_DIR = Path(__file__).resolve().parent

class WellnessReminder:
    def __init__(self):
        # Initialize tkinter root first (must be in main thread)
        self.tk_root = tk.Tk()
        self.tk_root.withdraw()  # Hide the main window
        
        # Queue for thread-safe GUI operations
        self.gui_queue = Queue()
        
        self.setup_logging()
        
        # Use absolute path for the database
        db_path = BASE_DIR / "data" / "wellness_reminders.json"
        self.db_manager = DatabaseManager(db_path)
        
        self.notification_manager = NotificationManager(self.db_manager)
        self.datetime_utils = DateTimeUtils()
        self.daily_reset_manager = DailyResetManager(self.db_manager)
        self.motivational = MotivationalMessages(self.db_manager)
        
        self.config = self.load_config()
        self.running = True
        self.last_check_date = None
        
        # Flag to prevent overlapping notifications
        self.notification_active = False
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        logging.info("Wellness Reminder Application initialized")
    
    def setup_logging(self):
        """Setup logging configuration"""
        # Use absolute path for the logs directory
        log_dir = BASE_DIR / "logs"
        log_dir.mkdir(exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                # Fix for UnicodeEncodeError by specifying UTF-8 encoding
                logging.FileHandler(log_dir / 'wellness_app.log', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
    
    def load_config(self):
        """Load reminder configuration from JSON file"""
        try:
            # Use absolute path for the config file
            with open(BASE_DIR / 'reminder_config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
            logging.info("Configuration loaded successfully")
            return config
        except FileNotFoundError:
            logging.error("reminder_config.json not found. Creating default configuration.")
            self.create_default_config()
            return self.load_config()
        except json.JSONDecodeError as e:
            logging.error(f"Error parsing configuration file: {e}")
            sys.exit(1)
    
    def create_default_config(self):
        """Create default configuration file"""
        # This function is now a fallback. The primary config is reminder_config.json
        default_config = {
                "reminders": {
                    "water": {
                    "interval_minutes": 75,
                    "messages": [
                        "💧 Time for some H2O! A hydrated mind is a sharp mind.",
                        "💧 Quick break for water! It's the easiest way to boost your energy.",
                        "💧 Don't forget to drink up! Your body will thank you.",
                        "💧 Stay hydrated, stay healthy. Time for a glass of water.",
                        "💧 Feeling sluggish? Water might be the answer. Have a sip!",
                        "💧 Let's raise a glass (of water) to your well-being!",
                        "💧 Hydration check! Have you had enough water today?"
                    ],
                    "enabled": True
                    },
                    "eye_rest": {
                    "interval_minutes": 20,
                    "messages": [
                        "👁️ Give your eyes a break. Look at something 20 feet away for 20 seconds.",
                        "👁️ Time for the 20-20-20 rule! Protect your peepers.",
                        "👁️ Your screen will be here when you get back. Rest your eyes.",
                        "👁️ Prevent eye strain! Look away from the screen now.",
                        "👁️ Blink, breathe, and look away. Your eyes deserve it.",
                        "👁️ A moment of rest for your eyes can prevent headaches later."
                    ],
                    "enabled": True
                    },
                    "stretch": {
                    "interval_minutes": 45,
                    "messages": [
                        "🧘 Time to stretch it out! Stand up and reach for the sky.",
                        "🧘 Loosen up! A quick stretch can release a lot of tension.",
                        "🧘 Your back and neck will thank you. Time for a stretch break.",
                        "🧘 Get the blood flowing! Stand up and move your body.",
                        "🧘 Sitting is the new smoking. Let's stand up and stretch!",
                        "🧘 Shake it off! A little movement goes a long way."
                    ],
                    "enabled": True
                    },
                    "lunch": {
                    "time": "13:30",
                    "messages": [
                        "🍽️ Lunch time! Step away from your desk and enjoy a proper meal.",
                        "🍽️ Fuel up! Your brain and body need energy to keep going.",
                        "🍽️ It's time to eat! Bon appétit!",
                        "🍽️ A mindful meal away from your screen can do wonders. Enjoy your lunch."
                    ],
                    "enabled": True
                    },
                    "end_day": {
                    "time": "19:30",
                    "messages": [
                        "🌅 Work is done! Time to close the laptop and enjoy your evening.",
                        "🌅 You've done enough for today. Time to wind down and relax.",
                        "🌅 The workday is over. Transition to your personal time, you've earned it!",
                        "🌅 Clocking out time! Leave work behind and focus on you."
                    ],
                    "enabled": True
                    }
                },
                "settings": {
                    "busy_delay_options": [
                        1,
                        5,
                        10
                    ],
                    "escalation_threshold": 2,
                    "escalation_window_hours": 2,
                    "data_retention_days": 30,
                    "notification_position": "bottom_right",
                    "compact_mode": True,
                    "auto_close_seconds": 45,
                    "motivational_cooldown_minutes": 30
                }
                }

        
        # Use absolute path for the config file
        with open(BASE_DIR / 'reminder_config.json', 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=2, ensure_ascii=False)
        
        logging.info("Default configuration created")
    
    def schedule_reminders(self):
        """Schedule all reminders based on configuration"""
        reminders = self.config['reminders']
        
        schedule.clear()
        
        for reminder_type, config in reminders.items():
            if not config.get('enabled', True):
                logging.info(f"Reminder {reminder_type} is disabled, skipping")
                continue
            
            # The message is chosen right before queuing to ensure variety
            if 'interval_minutes' in config:
                interval = config['interval_minutes']
                schedule.every(interval).minutes.do(
                    self.queue_reminder, 
                    reminder_type
                )
                logging.info(f"Scheduled {reminder_type} every {interval} minutes")
            elif 'time' in config:
                time_str = config['time']
                schedule.every().day.at(time_str).do(
                    self.queue_reminder,
                    reminder_type
                )
                logging.info(f"Scheduled {reminder_type} reminder at {time_str}")

        schedule.every().day.at("00:01").do(self.check_daily_reset)
        logging.info(f"Total scheduled jobs: {len(schedule.get_jobs())}")
    
    def queue_reminder(self, reminder_type):
        """Queue a reminder to be processed by the main thread"""
        # Get a fresh random message when it's time to queue the reminder
        messages = self.config['reminders'].get(reminder_type, {}).get("messages", ["Default message."])
        message_to_send = random.choice(messages)
        self.gui_queue.put(('reminder', reminder_type, message_to_send))
    
    def queue_motivational(self):
        """Queue a motivational message to be processed by the main thread"""
        self.gui_queue.put(('motivational',))
    
    def process_gui_queue(self):
        """Process GUI operations from the queue (runs in main thread)"""
        try:
            while not self.gui_queue.empty():
                item = self.gui_queue.get_nowait()
                
                if item[0] == 'reminder':
                    _, reminder_type, message = item
                    self.send_reminder_main_thread(reminder_type, message)
                elif item[0] == 'motivational':
                    self.show_motivational_main_thread()
                elif item[0] == 'startup':
                    self.show_startup_notification_main_thread()
                
        except Exception as e:
            logging.error(f"Error processing GUI queue: {e}")
        
        if self.running:
            self.tk_root.after(100, self.process_gui_queue)
    
    def send_reminder_main_thread(self, reminder_type, message):
        """Send a reminder notification in the main thread"""
        if self.notification_active:
            logging.warning(f"Skipping reminder '{reminder_type}' because another notification is already active.")
            return
            
        try:
            self.notification_active = True
            logging.info(f"Sending {reminder_type} reminder")
            response = self.notification_manager.show_reminder(reminder_type, message)
            
            # Handle response in a separate thread to not block the GUI
            threading.Thread(
                target=self.handle_reminder_response,
                args=(reminder_type, response),
                daemon=True
            ).start()
            
        except Exception as e:
            logging.error(f"Error sending reminder {reminder_type}: {e}")
        finally:
            self.notification_active = False

    def show_motivational_main_thread(self):
        """Show motivational message in the main thread"""
        try:
            self.motivational.show_motivational_message()
        except Exception as e:
            logging.error(f"Error showing motivational message: {e}")
    
    def show_startup_notification_main_thread(self):
        """Show startup notification in the main thread"""
        try:
            startup_message = "🌟 Wellness Reminder is now running in the background! Your first reminder will appear based on your schedule."
            
            from notifier import MotivationalDialog
            MotivationalDialog.show_motivational_message(startup_message)
            
        except Exception as e:
            logging.error(f"Error showing startup notification: {e}")
    
    def handle_reminder_response(self, reminder_type, response):
        """Handle user response to reminder"""
        try:
            response_type = response.get('action', 'skip')
            delay_minutes = response.get('delay_minutes', 0)
            
            logging.info(f"User response for {reminder_type}: {response_type} (delay: {delay_minutes})")
            
            rescheduled_time = None
            if response_type == 'busy' and delay_minutes > 0:
                rescheduled_time = datetime.now() + timedelta(minutes=delay_minutes)
            
            self.db_manager.log_reminder_response(
                reminder_type, 
                response_type, 
                delay_minutes,
                rescheduled_time
            )
            
            if response_type == 'busy' and delay_minutes > 0:
                def reschedule_reminder():
                    try:
                        logging.info(f"Sending rescheduled {reminder_type} reminder")
                        messages = self.config['reminders'][reminder_type]['messages']
                        original_message = random.choice(messages)
                        rescheduled_message = f"⏰ Rescheduled: {original_message}"
                        
                        self.gui_queue.put(('reminder', reminder_type, rescheduled_message))
                        
                    except Exception as e:
                        logging.error(f"Error sending rescheduled reminder: {e}")
                
                timer = threading.Timer(delay_minutes * 60, reschedule_reminder)
                timer.daemon = True
                timer.start()
                
                logging.info(f"Rescheduled {reminder_type} in {delay_minutes} minutes")
            
            # If user skipped, check if a motivational message is needed.
            # The skip tracker is no longer reset on 'ok'.
            if response_type == 'skip':
                # Check for escalation immediately after a skip
                if self.motivational.should_escalate():
                    logging.info("Queueing motivational message due to escalation.")
                    self.queue_motivational()
            elif response_type == 'ok':
                # Encouragement can still be shown without resetting the main skip counter
                if self.motivational.should_show_encouragement():
                    encouragement = self.motivational.get_encouragement_for_completion()
                    logging.info(f"Showing encouragement: {encouragement}")

        except Exception as e:
            logging.error(f"Error handling reminder response: {e}")
    
    def check_daily_reset(self):
        """Check if daily reset is needed"""
        try:
            if self.daily_reset_manager.should_reset():
                self.daily_reset_manager.perform_daily_reset()
                self.motivational.reset_daily_counters()
                logging.info("Daily reset completed")
        except Exception as e:
            logging.error(f"Error during daily reset: {e}")
    
    def run_scheduler(self):
        """Run the scheduler in a separate thread"""
        logging.info("Starting scheduler thread...")
        
        while self.running:
            try:
                schedule.run_pending()
                time.sleep(1)
            except Exception as e:
                logging.error(f"Error in scheduler loop: {e}")
                time.sleep(5)
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logging.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False
        if self.tk_root:
            self.tk_root.quit()
        if self.db_manager:
            self.db_manager.close()
        sys.exit(0)
    
    def run(self):
        """Main application loop - full scheduling mode"""
        try:
            logging.info("Starting Wellness Reminder Application in BACKGROUND MODE")
            
            # Reset database on every run for a fresh start
            logging.info("Clearing database for a fresh start...")
            self.db_manager.clear_all_data()
            self.db_manager.initialize_database()
            
            self.schedule_reminders()
            self.gui_queue.put(('startup',))
            
            scheduler_thread = threading.Thread(target=self.run_scheduler, daemon=True)
            scheduler_thread.start()
            
            self.process_gui_queue()
            
            logging.info("Application started successfully. Running in background...")
            logging.info("Press Ctrl+C to stop the application")
            
            try:
                self.tk_root.mainloop()
            except KeyboardInterrupt:
                logging.info("Application interrupted by user")
                self.running = False
                
        except Exception as e:
            logging.error(f"Fatal error: {e}")
        finally:
            logging.info("Application shutting down")
            if self.db_manager:
                self.db_manager.close()
            self.running = False
    
    def run_test_mode(self):
        """Run in test mode - single reminder for testing"""
        try:
            logging.info("Starting Wellness Reminder Application in TEST MODE")
            
            self.db_manager.clear_all_data()
            self.db_manager.initialize_database()
            
            if self.motivational.should_escalate():
                self.motivational.show_motivational_message()
                return
            
            reminder_type = "water"
            messages = self.config['reminders']['water']['messages']
            message = random.choice(messages)
            
            logging.info(f"Sending test reminder: {reminder_type}")
            
            response = self.notification_manager.show_reminder(reminder_type, message)
            
            self.handle_reminder_response(reminder_type, response)
            
            logging.info(f"Test completed. Response: {response}")
            
        except Exception as e:
            logging.error(f"Error in test mode: {e}")
        finally:
            if self.db_manager:
                self.db_manager.close()

def main():
    """Main entry point with command line argument support"""
    app = WellnessReminder()
    
    if len(sys.argv) > 1:
        if sys.argv[1].lower() == 'test':
            print("Running in TEST mode...")
            app.run_test_mode()
        elif sys.argv[1].lower() == 'help':
            print("\nWellness Reminder Application")
            print("Usage:")
            print("  python main.py        - Run in background mode (full scheduling)")
            print("  python main.py test   - Run single test reminder")
            print("  python main.py help   - Show this help")
            print("\nBackground mode will run continuously until stopped with Ctrl+C")
        else:
            print(f"Unknown argument: {sys.argv[1]}")
            print("Use 'python main.py help' for usage information")
    else:
        print("Starting Wellness Reminder in background mode...")
        print("The application will run continuously in the background.")
        print("Press Ctrl+C to stop.")
        app.run()

if __name__ == "__main__":
    main()
