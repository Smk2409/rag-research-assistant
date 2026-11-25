#!/usr/bin/env python3
"""Get a Cognito ID token for CLI testing / the evaluation script.
Usage: python scripts/get_token.py <client_id> <email> <password> [region]"""
import sys, boto3
client_id, email, password = sys.argv[1:4]
region = sys.argv[4] if len(sys.argv) > 4 else "us-east-1"
r = boto3.client("cognito-idp", region_name=region).initiate_auth(
    ClientId=client_id, AuthFlow="USER_PASSWORD_AUTH", AuthParameters={"USERNAME": email, "PASSWORD": password})
print(r["AuthenticationResult"]["IdToken"])
