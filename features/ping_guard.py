# OOOZet - Bot społeczności OOOZ
# Copyright (C) 2023-2026 Karol "digitcrusher" Łacina
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import asyncio, discord

import database
from common import config, parse_duration
from features.warns import warns_of

bot = None
lock = asyncio.Lock()

async def setup(_bot):
  global bot
  bot = _bot

  async def ping_role(interaction, msg):
    async def on_submit(interaction):
      role = select.values[0]

      async with lock: # Guards against TOCTOU attacks on cooldowns.
        last_use = database.data.get('ping_role_last_use', {}).get(interaction.user.id)
        if last_use is not None and (interaction.created_at - last_use).total_seconds() < parse_duration(config['ping_role_cooldown']):
          await interaction.response.send_message('Musisz zaczekać, aby móc ponownie użyć tej komendy. ⏱️', ephemeral=True)
          return

        is_authorized = False
        authorizing_rule = None
        role_is_unlockable = False
        rules_not_satisfied_msg = f'Nie możesz pingnąć {role.mention}, ponieważ:\n'

        if role.mentionable or interaction.permissions.mention_everyone:
          is_authorized = True
        else:
          for rule in config['ping_role_rules']:
            if role.id not in rule['unlocked_roles']:
              continue
            role_is_unlockable = True

            if rule['required_role'] is not None and interaction.user.get_role(rule['required_role']) is None:
              rules_not_satisfied_msg += f'- Nie masz roli <@&{rule["required_role"]}>. 😢\n'
              continue

            if not rule['can_have_warns'] and warns_of(interaction.user.id):
              rules_not_satisfied_msg += '- Masz lub miałeś ostrzeżenia. 😒\n'
              continue

            cooldown = parse_duration(rule['cooldown'])
            if rule['cooldown_is_per_user']:
              last_use = database.data.get('ping_role_rule_last_use', {}).get(rule['id'], {}).get(interaction.user.id)
              if last_use is not None and (interaction.created_at - last_use).total_seconds() < cooldown:
                rules_not_satisfied_msg += '- Już pingnąłeś tę rolę niedawno. ⏱️\n'
                continue
            else:
              last_use = database.data.get('ping_role_rule_last_use', {}).get(rule['id'])
              if last_use is not None and (interaction.created_at - last_use).total_seconds() < cooldown:
                rules_not_satisfied_msg += '- Ktoś niedawno już pingnął tę rolę. ⏱️\n'
                continue

            is_authorized = True
            authorizing_rule = rule
            break

        if not is_authorized:
          if role_is_unlockable:
            await interaction.response.send_message(rules_not_satisfied_msg, ephemeral=True)
          else:
            await interaction.response.send_message('Nie można pingować tej roli… 🙄', ephemeral=True)
          return

        if not role.mentionable and not interaction.app_permissions.mention_everyone:
          await interaction.response.send_message(f'Nie mam uprawnień, żeby spingować {role.mention}… 🧐', ephemeral=True)
          return
        new_msg = await msg.channel.send(
          f'{role.mention} {msg.content}\n-# Wysłane przez {interaction.user.mention}',
          files=await asyncio.gather(*(i.to_file(use_cached=True) for i in msg.attachments)),
          allowed_mentions=discord.AllowedMentions(roles=[role]),
        )

        database.data.setdefault('ping_role_last_use', {})[interaction.user.id] = new_msg.created_at
        if authorizing_rule is not None:
          if authorizing_rule['cooldown_is_per_user']:
            database.data.setdefault('ping_role_rule_last_use', {}).setdefault(authorizing_rule['id'], {})[interaction.user.id] = new_msg.created_at
          else:
            database.data.setdefault('ping_role_rule_last_use', {})[authorizing_rule['id']] = new_msg.created_at
        database.should_save = True

        try:
          await msg.delete()
        except discord.NotFound:
          pass
        except discord.Forbidden:
          await interaction.response.send_message('Nie mam uprawnień do usuwania wiadomości… 🧐', ephemeral=True)
          return

        await interaction.response.defer()

    select = discord.ui.RoleSelect()
    modal = discord.ui.Modal(title='Dodaj ping roli do wiadomości')
    modal.on_submit = on_submit
    modal.add_item(discord.ui.TextDisplay('> ' + msg.content.rstrip().replace('\n', '\n> ')))
    modal.add_item(discord.ui.Label(text='Rola, którą chcesz pingnąć', component=select))
    modal.add_item(discord.ui.TextDisplay('Bot usunie twoją wiadomość i wyśle ją ponownie z dodanym pingiem i podpisem, że jest twoja.'))
    await interaction.response.send_modal(modal)

  @bot.tree.command(name='ping-role', description='Dodaje ping roli do twojej ostatniej wiadomości na tym kanale')
  @discord.app_commands.guilds(config['guild'])
  async def cmd_ping_role(interaction):
    async for msg in interaction.channel.history(oldest_first=False):
      if msg.author == interaction.user:
        await ping_role(interaction, msg)
        return

    await interaction.response.send_message('Żadna z ostatnich wiadomości na tym kanale nie jest twoja… 😐', ephemeral=True)

  @bot.tree.context_menu(name='Dodaj ping roli')
  @discord.app_commands.guilds(config['guild'])
  async def menu_ping_role(interaction, msg: discord.Message):
    if msg.author != interaction.user:
      await interaction.response.send_message('To nie jest twoja wiadomość… 🤨', ephemeral=True)
      return

    await ping_role(interaction, msg)
