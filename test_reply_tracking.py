#!/usr/bin/env python3
"""
Test script for the new reply detection functionality.
Run this locally to test the reply logic without starting the bot.
"""

class MockUser:
    def __init__(self, id, name):
        self.id = id
        self.name = name
        self.mention = f"<@{id}>"
    
    def __repr__(self):
        return f"User({self.name})"

class MockMessage:
    def __init__(self, content, author, mentions=None):
        self.content = content
        self.author = author
        self.mentions = mentions or []
    
    def __repr__(self):
        return f"Message(content={repr(self.content)}, author={self.author})"

def should_ping_original_poster(reply_content, replied_message, replier, bot_user):
    """
    Test function to determine if we should ping the original poster
    Returns: (should_ping: bool, reason: str, original_poster: MockUser|None)
    """
    # Check for opt-out flags in the reply first
    opt_out_flags = ['--no-ping', '--noping', '--silent', '-np']
    message_lower = reply_content.lower()
    if any(flag in message_lower for flag in opt_out_flags):
        return False, "Opt-out flag detected", None
    
    # Check if it's a message from Brad (the bot)
    if replied_message.author != bot_user:
        return False, "Not replying to a bot message", None
    
    # Look for mentions in Brad's message to find the original poster
    if not replied_message.mentions:
        return False, "No mentions in bot message", None
    
    # The first mention should be the original poster
    original_poster = replied_message.mentions[0]
    
    # Don't ping if the replier is the original poster
    if replier.id == original_poster.id:
        return False, "Replier is the original poster", original_poster
    
    return True, f"Should ping {original_poster.name}", original_poster

def test_reply_detection():
    """Test cases for the new reply detection functionality"""
    print("Testing New Reply Detection Functionality")
    print("=" * 60)
    
    # Setup test users
    bot_user = MockUser(12345, "Brad")
    alice = MockUser(98765, "Alice")
    bob = MockUser(87654, "Bob")
    charlie = MockUser(76543, "Charlie")
    
    # Setup test messages (Brad's responses to different users)
    brad_msg_alice = MockMessage("@Alice: Check out [Example Site](<https://example.com>)", bot_user, [alice])
    brad_msg_bob = MockMessage("@Bob: Visit [GitHub](<https://github.com>)", bot_user, [bob])
    brad_msg_no_mention = MockMessage("Here's a link: https://example.com", bot_user, [])
    alice_original_msg = MockMessage("Check out https://example.com", alice, [])
    
    test_cases = [
        # Format: (reply_content, replied_message, replier, expected_should_ping, description)
        ("Great link!", brad_msg_alice, bob, True, "Bob replies to Alice's link via Brad"),
        ("Thanks --no-ping", brad_msg_alice, bob, False, "Bob replies with --no-ping flag"),
        ("Cool --noping stuff", brad_msg_alice, bob, False, "Bob replies with --noping flag"),
        ("Nice --silent", brad_msg_alice, bob, False, "Bob replies with --silent flag"),
        ("Awesome -np", brad_msg_alice, bob, False, "Bob replies with -np flag"),
        ("Thanks!", brad_msg_alice, alice, False, "Alice replies to her own link"),
        ("Reply", alice_original_msg, bob, False, "Reply to non-bot message"),
        ("This has --NO-PING in caps", brad_msg_alice, bob, False, "Case insensitive opt-out flag"),
        ("Interesting", brad_msg_no_mention, bob, False, "Reply to Brad message with no mentions"),
        ("Multiple --noping flags --no-ping", brad_msg_alice, charlie, False, "Multiple opt-out flags"),
        ("Love this!", brad_msg_bob, alice, True, "Alice replies to Bob's link via Brad"),
    ]
    
    passed = 0
    total = len(test_cases)
    
    for i, (reply_content, replied_msg, replier, expected, description) in enumerate(test_cases, 1):
        should_ping, reason, original_poster = should_ping_original_poster(reply_content, replied_msg, replier, bot_user)
        status = "PASS" if should_ping == expected else "FAIL"
        
        print(f"Test {i:2d}: {status} - {description}")
        print(f"         Reply: {repr(reply_content)}")
        print(f"         Replied to: {replied_msg}")
        print(f"         Replier: {replier}")
        print(f"         Result: {should_ping} ({reason})")
        if original_poster:
            print(f"         Would ping: {original_poster}")
        if should_ping != expected:
            print(f"         Expected: {expected}")
        else:
            passed += 1
        print()
    
    print("=" * 60)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed!")
    else:
        print(f"❌ {total - passed} tests failed")
    
    return passed == total

def interactive_test():
    """Interactive testing mode for reply detection"""
    print("\n" + "=" * 60)
    print("Interactive Reply Detection Test")
    print("=" * 60)
    print("Commands:")
    print("  test '<reply_content>' <replier_name> <original_poster_name> - Test reply scenario")
    print("  show - Show available users")
    print("  quit - Exit interactive mode\n")
    
    # Available users
    users = {
        'brad': MockUser(12345, "Brad"),
        'alice': MockUser(98765, "Alice"),
        'bob': MockUser(87654, "Bob"),
        'charlie': MockUser(76543, "Charlie"),
    }
    bot_user = users['brad']
    
    while True:
        try:
            command = input("Command: ").strip()
            if command.lower() == 'quit':
                break
            
            if command.lower() == 'show':
                print("Available users:")
                for name, user in users.items():
                    print(f"  {name}: {user}")
                continue
            
            # Parse test command
            if command.startswith("test "):
                # Extract quoted reply content and user names
                import shlex
                try:
                    parts = shlex.split(command[5:])  # Remove "test " prefix
                    if len(parts) != 3:
                        print("Usage: test '<reply_content>' <replier_name> <original_poster_name>")
                        continue
                    
                    reply_content, replier_name, original_poster_name = parts
                    
                    if replier_name not in users or original_poster_name not in users:
                        print(f"Unknown users. Available: {list(users.keys())}")
                        continue
                    
                    replier = users[replier_name]
                    original_poster = users[original_poster_name]
                    
                    # Create Brad's message mentioning the original poster
                    brad_message = MockMessage(f"@{original_poster.name}: [Link](<https://example.com>)", 
                                             bot_user, [original_poster])
                    
                    should_ping, reason, pinged_user = should_ping_original_poster(
                        reply_content, brad_message, replier, bot_user)
                    
                    print(f"Scenario: {replier.name} replies '{reply_content}' to Brad's message for {original_poster.name}")
                    print(f"Result: {'PING' if should_ping else 'NO PING'} - {reason}")
                    if pinged_user:
                        print(f"Would ping: {pinged_user}")
                    print()
                    
                except ValueError as e:
                    print(f"Parse error: {e}")
                    print("Usage: test '<reply_content>' <replier_name> <original_poster_name>")
            else:
                print("Unknown command. Try 'show', 'test', or 'quit'")
                
        except KeyboardInterrupt:
            print("\nExiting interactive mode...")
            break
        except EOFError:
            break

if __name__ == "__main__":
    # Run automated tests
    all_passed = test_reply_detection()
    
    # Offer interactive testing
    choice = input("\nWould you like to run interactive tests? (y/n): ").strip().lower()
    if choice in ['y', 'yes']:
        interactive_test()
    
    print("\nDone!")
