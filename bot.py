import os
import discord
from discord.ext import tasks
from app import create_app, db
from app.models import User, Notification
import asyncio

# Config
GUILD_ID = 1407095652718215480
VERIFIED_ROLE_ID = 1407095970650521681
TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.members = True
intents.messages = True

client = discord.Client(intents=intents)
app = create_app()

@client.event
async def on_ready():
    print(f'Logged in as {client.user}')
    process_tasks.start()

@tasks.loop(seconds=10)
async def process_tasks():
    with app.app_context():
        await process_verifications()
        await process_notifications()

async def process_verifications():
    users = User.query.filter_by(discord_verification_requested=True).all()
    guild = client.get_guild(GUILD_ID)

    if not guild:
        # Guild might not be in cache yet or bot not in guild
        # Try fetching
        try:
            guild = await client.fetch_guild(GUILD_ID)
        except:
            print(f"Guild {GUILD_ID} not accessible.")
            return

    role = guild.get_role(VERIFIED_ROLE_ID)
    if not role:
        # Role might not be in cache, fetch roles?
        # Roles are usually cached with guild.
        # Check if role exists in guild roles
        role = discord.utils.get(guild.roles, id=VERIFIED_ROLE_ID)
        if not role:
            print(f"Role {VERIFIED_ROLE_ID} not found in guild.")
            return

    for user in users:
        if not user.discord_id:
            user.discord_verification_requested = False
            db.session.commit()
            continue

        try:
            member = await guild.fetch_member(int(user.discord_id))
        except discord.NotFound:
            print(f"User {user.discord_id} not found in guild.")
            user.discord_verification_requested = False
            db.session.commit()
            continue
        except ValueError:
            print(f"Invalid Discord ID for user {user.id}")
            user.discord_verification_requested = False
            db.session.commit()
            continue
        except Exception as e:
            print(f"Error fetching member {user.discord_id}: {e}")
            continue

        # Update Member
        try:
            new_nick = f"{user.first_name} {user.last_name}"
            # Only change if different to avoid API spam/limits?
            if member.display_name != new_nick:
                await member.edit(nick=new_nick)

            if role not in member.roles:
                await member.add_roles(role)

            # Send DM
            try:
                await member.send(f"¡Verificación exitosa! Bienvenido a Gobierno de San Andreas, {user.first_name}.")
            except discord.Forbidden:
                pass # Can't DM

            user.discord_verification_requested = False
            db.session.commit()
            print(f"Verified {user.first_name} {user.last_name}")

        except discord.Forbidden:
            print(f"Permission denied modifying {member.display_name}. Check Bot Role Position.")
            # We mark as done to avoid infinite loop of failures
            user.discord_verification_requested = False
            db.session.commit()
        except Exception as e:
            print(f"Error verifying {member.display_name}: {e}")

async def process_notifications():
    notifs = Notification.query.filter_by(status='pending').all()
    for notif in notifs:
        user = notif.user
        if not user.discord_id:
            notif.status = 'failed_no_id'
            db.session.commit()
            continue

        try:
            discord_user = await client.fetch_user(int(user.discord_id))
            await discord_user.send(notif.content)
            notif.status = 'sent'
        except discord.NotFound:
            notif.status = 'failed_not_found'
        except discord.Forbidden:
            notif.status = 'failed_dm_closed'
        except Exception as e:
            print(f"Error sending notification to {user.id}: {e}")
            notif.status = 'error'

        db.session.commit()

if __name__ == '__main__':
    if not TOKEN:
        print("Error: DISCORD_TOKEN environment variable not set.")
        print("Please set export DISCORD_TOKEN='your_token_here'")
    else:
        client.run(TOKEN)
