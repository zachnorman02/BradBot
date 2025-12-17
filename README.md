# BradBot Features
-# Note: commands that currently do not work, and restricted commands (such as bot owner commands), will not be listed here

## /admin 
-# for those with admin privileges only
**/admin auditlog:** query audit log with SQL-like syntax
**/admin maintenance assignlvl0:** assign level 0 role to all verified members without another level role
**/admin maintanence kickunverified:** Kick unverified members with no open ticket after 30 days. Optional dry run parameter to see who would get kicked before actually kicking- defaults to true
**/admin menu:** Open server settings menu
**/admin panel:** Same as menu, except a persistent message rather than a temporary one
**/admin tools autorole:** Configure automatic rule assignment rules. Role parameters are comma-delimited (ie @lvl0, @lvl1, ...)
**/admin tools channelrestriction:** Configure channel access restrictions based on roles
**/admin tools conditionalrole:** Manage conditional role assignments w/ blocking roles
**/admin tools loadboosterroles:** Load existing booster roles into the database
**/admin tools messagemirror:** Configure message mirroring between channels
**/admin tools saveboosterrole:** Manually save a booster role to the database. Can manually set a particular user or user_id who the role belongs to if it doesn't currently belong to anyone

## /booster
-# Note: these apply to the user running the command
**/booster role color**: Set color on personal booster role. Hex values all optional for holographic, hex3 optional for gradient, hex2 optional for soli
**/booster role icon:** Set icon url for booster role
**/booste role label:** Set booster role name

## /emoji
-# Requires perms for emoji management. Also allows sticker management
**/emoji copy:** Copy emoji from a message
**/emoji db list:** List saved emojis/stickers
**/emoji db load:** Add saved emoji/sticker from database
**/emoji db save:** Save emoji/sticker to database to reference later
**/emoji db saveserver:** Save emojis from the server to the database
**/emoji from_attachment:** Create emoji from a message attachment
**/emoji reaction:** Save emoji from a message reaction
**/emoji remove:** Remove emoji/sticker from server
**/emoji rename:** Rename emoji/sticker
**/emoji upload:** Upload custom emoji from image URL

## /issues
**/issues panel:** Persistent panel for GitHub issue submission

## /poll
**/poll close :** Close particular poll
**/poll create:** Create new poll
**/poll list:** List all active polls in the server
**/poll refresh:** Refresh poll to fix button issues
**/poll reopen:** Reopen closed poll
**/poll results:** View responses to a poll
**/poll stats:** View stats of a poll
**/poll wordcloud:** Make wordcloud of poll responses 

## /settings
**/settings menu:** Open user-level settings for BradBot
**/settings notify:** Toggle reply notificatons if someone replies to your fixed links
**/settings sendpings:** Toggle whether your replies trigger a ping to the original poster

## Other commands
**/tconvert :** Convert between injection and gel dosage
**/timestamp:** Generate Discord timestamps

## /utility
**/utility remind:** Set reminder 
**/utility timer:**Set timer

## /voice
**/voice filter_voices:** Filter available voices by language and engine
**/voice join:** Join either current vc or specified channel
**/voice leave:** Leave vc
**/voice show_tts_options:** Show all available options for TTS parameters
**/voice tts:** Speak text via TTS into the voice channel
