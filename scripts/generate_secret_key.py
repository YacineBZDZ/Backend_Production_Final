import secrets
import base64

# Generate a 32-byte (256-bit) random key
random_bytes = secrets.token_bytes(32)

# Convert to a URL-safe base64-encoded string
secret_key = base64.urlsafe_b64encode(random_bytes).decode('utf-8')

print("Your new secure JWT_SECRET_KEY:")
print(secret_key)

# Alternative: Generate a hex string (64 characters for 32 bytes)
hex_key = secrets.token_hex(32)
print("\nAlternative hex format:")
print(hex_key)
