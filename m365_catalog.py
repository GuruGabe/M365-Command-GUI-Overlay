# =============================================================================
# Script:   m365_catalog.py
# Author:   Gabriel Clifton (built with Claude)
# Created:  10-23-2026 (moved out of M365GUI.py, v0.6)
# Modified: 10-23-2026
#
# Purpose:
#   M365GUI's task catalog (every form: its m365 command template and boxes)
#   and the command builder that turns a filled-in form into the argument
#   list m365 runs. No window code here - like GAMGUI's gam_catalog.py.
# =============================================================================

import re

# =============================================================================
# SECTION: Task catalog (all commands verified against m365 v11 --help)
#   template uses "--flag {value}" style; {placeholders} fill from the form,
#   [bracketed] parts drop when blank, bare flags (--force) are literal.
# =============================================================================

def T(name, desc, template, fields, destructive=False, workflow=""):
    return {"name": name, "desc": desc, "template": template,
            "fields": fields, "destructive": destructive, "workflow": workflow}

def F(label, key, required=True, choices=None, default=""):
    return {"label": label, "key": key, "required": required,
            "choices": choices, "default": default}

# The 'Afterwards' choices of the OneDrive copy (see transfer_onedrive).
TRANSFER_ACCESS_REMOVE = "Remove my temporary access when done"
TRANSFER_ACCESS_KEEP = "Keep my access to both OneDrives"

# The 'Which links' choices of Files shared by link (see shared_links, v0.14).
SHARE_ANYONE = "Anyone-with-the-link links only"
SHARE_ALL = "Every sharing link"

TASKS = {
 "Users (Entra ID)": [
  T("List users", "Lists all users in the directory.",
    "entra user list --output text", []),
  T("List guest users", "Lists only external / guest accounts.",
    "entra user list --type Guest --output text", []),
  T("Get user info", "Shows the details of one user, found by their UPN.",
    "entra user get --userName {email} --output text",
    [F("User (UPN) e.g. jdoe@contoso.com", "email")]),
  T("Create user",
    "Creates a new member account. Set the usage location so the account can "
    "be licensed later.",
    "entra user add --displayName {display} --userName {email} --password {password} [--usageLocation {loc}]",
    [F("Display name e.g. John Doe", "display"),
     F("User (UPN) e.g. jdoe@contoso.com", "email"),
     F("Initial password", "password"),
     F("Usage location e.g. US (optional)", "loc", False)]),
  T("Reset password",
    "Sets a new password and forces a change at next sign-in.",
    "entra user set --userName {email} --resetPassword --newPassword {password} --forceChangePasswordNextSignIn",
    [F("User (UPN)", "email"), F("New password", "password")]),
  T("Rename user (display / first / last name)",
    "Changes the user's names. The sign-in name (UPN) does not change.",
    "entra user set --userName {email} [--displayName {display}] [--firstName {first}] [--lastName {last}]",
    [F("User (UPN)", "email"), F("New display name (optional)", "display", False),
     F("New first name (optional)", "first", False),
     F("New last name (optional)", "last", False)]),
  T("Set usage location",
    "Sets the country the account is used from (required before assigning "
    "licenses).",
    "entra user set --userName {email} --usageLocation {loc}",
    [F("User (UPN)", "email"), F("Usage location e.g. US", "loc")]),
  T("Block sign-in",
    "Disables the account so the user cannot sign in; keeps the account/data.",
    "entra user set --userName {email} --accountEnabled false",
    [F("User (UPN)", "email")]),
  T("Unblock sign-in", "Re-enables a blocked account.",
    "entra user set --userName {email} --accountEnabled true",
    [F("User (UPN)", "email")]),
  T("Delete user (DESTRUCTIVE)",
    "Deletes the account (recoverable from the Entra recycle bin for 30 days).",
    "entra user remove --userName {email} --force",
    [F("User (UPN)", "email")], destructive=True),
  T("List deleted users (recycle bin)",
    "Lists users that were deleted within the last 30 days.",
    "entra user recyclebinitem list --output text", []),
  T("Restore deleted user",
    "Restores a soft-deleted user by their object id (from the recycle bin "
    "list).",
    "entra user recyclebinitem restore --id {id}",
    [F("User object id (from recycle bin list)", "id")]),
  # ---- v0.8: guided workflow (m365_workflows.staff_handoff) -----------------
  T("Staff hand-off - someone is leaving",
    "Saves a record of the person's groups and licenses, then does the steps chosen below "
    "in a safe order: block sign-in, sign them out, copy their OneDrive files to their "
    "manager (while the license still exists), set an automatic reply, remove them from "
    "their groups, remove their licenses. Asks once before changing anything. Removing "
    "licenses deletes their mailbox 30 days later - it is No by default.",
    "", [F("Leaver (UPN)", "leaver"),
         F("Their manager (UPN) - gets the OneDrive files", "manager", False),
         F("Block sign-in", "block", choices=["Yes", "No"], default="Yes"),
         F("Sign them out everywhere", "signout", choices=["Yes", "No"], default="Yes"),
         F("Copy their OneDrive files to the manager", "copy", choices=["Yes", "No"], default="Yes"),
         F("Set an automatic reply (needs rights to their mailbox)", "autoreply",
           choices=["Yes", "No"], default="No"),
         F("Automatic reply message", "reply", False),
         F("Remove them from every group", "groups", choices=["Yes", "No"], default="No"),
         F("Remove their licenses (mailbox deleted 30 days later)", "licenses",
           choices=["Yes", "No"], default="No")],
    workflow="staff_handoff"),
  # ---- v0.7 (10-23-2026): options checked against the CLI's docs ----------
  T("List members only (no guests)", "Lists the organization's own accounts, without guests.",
    "entra user list --type Member --output text", []),
  T("Get user info with their manager",
    "Shows one user's details and who their manager is.",
    "entra user get --userName {email} --withManager --output text",
    [F("User (UPN)", "email")]),
  T("Groups a user belongs to", "Lists every group the user is a member of.",
    "entra user groupmembership list --userName {email} --output text",
    [F("User (UPN)", "email")]),
  T("A user's licenses", "Lists the licenses assigned to one user.",
    "entra user license list --userName {email} --output text",
    [F("User (UPN)", "email")]),
  T("Set job title / department / office",
    "Changes a user's job title, department, office location or company name. "
    "Blank boxes are left as they are.",
    "entra user set --userName {email} [--jobTitle {title}] [--department {dept}] "
    "[--officeLocation {office}] [--companyName {company}]",
    [F("User (UPN)", "email"), F("Job title (optional)", "title", False),
     F("Department (optional)", "dept", False), F("Office location (optional)", "office", False),
     F("Company name (optional)", "company", False)]),
  T("Set a user's manager", "Sets who the user reports to.",
    "entra user set --userName {email} --managerUserName {manager}",
    [F("User (UPN)", "email"), F("Manager (UPN)", "manager")]),
  T("Remove a user's manager", "Clears who the user reports to.",
    "entra user set --userName {email} --removeManager",
    [F("User (UPN)", "email")]),
  T("Invite a guest (external user)",
    "Invites someone outside the organization and emails them the invitation.",
    "entra user guest add --emailAddress {email} [--displayName {display}] "
    "[--welcomeMessage {message}] --sendInvitationMessage",
    [F("Their email address", "email"), F("Display name (optional)", "display", False),
     F("Welcome message (optional)", "message", False)]),
  T("Check a password against the policy",
    "Tells you whether a password meets the organization's password rules - "
    "nothing is changed. (Microsoft marks this API as preview.)",
    "entra user password validate --password {password} --output text",
    [F("Password to check", "password")]),
  T("MFA / sign-in methods report",
    "Who has registered multi-factor authentication and which methods. "
    "Needs the AuditLog.Read.All permission and an Entra ID P1/P2 tenant.",
    "entra user registrationdetails list [--isMfaRegistered {mfa}] [--userType {utype}] --output text",
    [F("Only users registered for MFA? (blank = everyone)", "mfa", False, choices=["", "true", "false"]),
     F("Members or guests (blank = both)", "utype", False, choices=["", "member", "guest"])]),
  T("Permanently delete a user from the recycle bin (DESTRUCTIVE)",
    "Deletes a deleted user for good - it can NOT be restored afterwards. Get the "
    "id from 'List deleted users (recycle bin)'.",
    "entra user recyclebinitem remove --id {id} --force",
    [F("User object id (from recycle bin list)", "id")], destructive=True),
  T("Empty the user recycle bin (DESTRUCTIVE)",
    "Permanently deletes EVERY user in the recycle bin - none can be restored afterwards.",
    "entra user recyclebinitem clear --force", [], destructive=True),
  T("Remove ALL guest users (DESTRUCTIVE)",
    "Finds every guest account, shows you the count, asks you to type DELETE, "
    "then removes them one by one. Nothing is deleted until you confirm.",
    "", [], destructive=True, workflow="remove_guests"),
 ],
 "Groups (Entra)": [
  T("List groups", "Lists all groups in the directory.",
    "entra group list --output text", []),
  T("List groups by type", "Lists only one kind of group.",
    "entra group list --type {type} --output text",
    [F("Type", "type", choices=["microsoft365", "security", "distribution", "mailEnabledSecurity"])]),
  T("Rename a group / change its description",
    "Gives a group a new display name and/or description. Blank boxes are left as they are.",
    "entra group set --displayName {name} [--newDisplayName {newname}] [--description {desc}]",
    [F("Group display name", "name"), F("New display name (optional)", "newname", False),
     F("New description (optional)", "desc", False)]),
  T("Make a member an owner (or back to member)",
    "Changes a group member's role.",
    "entra group member set --groupName {name} --userNames {email} --role {role}",
    [F("Group display name", "name"), F("User (UPN)", "email"),
     F("New role", "role", choices=["Owner", "Member"])]),
  T("Get group info", "Shows the details of one group, found by its name.",
    "entra group get --displayName {name} --output text",
    [F("Group display name", "name")]),
  T("Create group",
    "Creates a Microsoft 365 or security group.",
    "entra group add --displayName {name} --type {type} [--mailNickname {nick}] [--description {desc}]",
    [F("Group display name", "name"),
     F("Type", "type", choices=["microsoft365", "security"]),
     F("Mail nickname (M365 groups) e.g. sales (optional)", "nick", False),
     F("Description (optional)", "desc", False)]),
  T("List group members", "Lists the members of a group.",
    "entra group member list --groupName {name} --output text",
    [F("Group display name", "name")]),
  T("Add member to group", "Adds a user to a group with the chosen role.",
    "entra group member add --groupName {name} --userNames {email} --role {role}",
    [F("Group display name", "name"), F("User (UPN)", "email"),
     F("Role", "role", choices=["Member", "Owner"])]),
  T("Remove member from group (DESTRUCTIVE)", "Removes a user from a group.",
    "entra group member remove --groupName {name} --userNames {email} --force",
    [F("Group display name", "name"), F("User (UPN)", "email")],
    destructive=True),
  T("Delete group (DESTRUCTIVE)", "Deletes a group (not its members' accounts).",
    "entra group remove --displayName {name} --force",
    [F("Group display name", "name")], destructive=True),
 ],
 "Licenses": [
  T("View all licenses (tenant SKUs)",
    "Lists the license SKUs your tenant owns, with used/total counts and each "
    "SKU's id (needed for the tasks below).",
    "entra license list --output text", []),
  T("List users with a specific license",
    "Lists every user assigned a given license. Get the SKU id from 'View all "
    "licenses' (the skuId GUID).",
    "entra user list --properties \"displayName,userPrincipalName,assignedLicenses\" "
    "--query \"[?assignedLicenses[?skuId=='{skuId}']].{displayName:displayName,userPrincipalName:userPrincipalName}\" --output text",
    [F("License SKU id (GUID, from View all licenses)", "skuId")]),
  T("Assign license(s)",
    "Assigns one or more license SKUs (comma-separated ids) to a user. The "
    "user must have a usage location set.",
    "entra user license add --userName {email} --ids {ids}",
    [F("User (UPN)", "email"), F("License SKU id(s), comma-separated", "ids")]),
  T("Remove license(s) (DESTRUCTIVE)",
    "Removes one or more license SKUs from a user.",
    "entra user license remove --userName {email} --ids {ids} --force",
    [F("User (UPN)", "email"), F("License SKU id(s), comma-separated", "ids")],
    destructive=True),
 ],
 "Teams / M365 Groups": [
  T("Add member to a Team",
    "Adds a user to a Microsoft Team (M365 group) as Member or Owner.",
    "entra m365group user add --teamName {team} --userNames {email} --role {role}",
    [F("Team display name e.g. Engineering", "team"), F("User (UPN)", "email"),
     F("Role", "role", choices=["Member", "Owner"])]),
  # ---- v0.7 (10-23-2026): options checked against the CLI's docs ----------
  T("List Microsoft 365 groups",
    "Every Microsoft 365 group (every Team has one). For a group's SharePoint site, use "
    "SharePoint > List team or communication sites.",
    "entra m365group list --output text", []),
  T("Microsoft 365 groups without owners",
    "Groups nobody owns - nobody can manage their members or settings.",
    "entra m365group list --orphaned --output text", []),
  T("Get a Team / Microsoft 365 group's info",
    "Shows one Microsoft 365 group (or Team).",
    "entra m365group get --displayName {team} --output text",
    [F("Team / group display name", "team")]),
  T("List a Team's members and owners",
    "Lists who is in a Team / Microsoft 365 group. Choose a role to see only owners or members.",
    "entra m365group user list --groupDisplayName {team} [--role {role}] --output text",
    [F("Team / group display name", "team"),
     F("Only this role (blank = everyone)", "role", False, choices=["", "Owner", "Member"])]),
  T("Change someone's role in a Team",
    "Makes a Team member an owner, or an owner a member.",
    "entra m365group user set --teamName {team} --userNames {email} --role {role}",
    [F("Team display name", "team"), F("User (UPN)", "email"),
     F("New role", "role", choices=["Owner", "Member"])]),
  T("Remove someone from a Team (DESTRUCTIVE)",
    "Removes a member or owner from a Team / Microsoft 365 group.",
    "entra m365group user remove --teamName {team} --userNames {email} --force",
    [F("Team display name", "team"), F("User (UPN)", "email")], destructive=True),
  T("Turn a Microsoft 365 group into a Team",
    "Adds Microsoft Teams to an existing Microsoft 365 group.",
    "entra m365group teamify --displayName {team}",
    [F("Group display name", "team")]),
  T("Deleted Microsoft 365 groups (recycle bin)",
    "Microsoft 365 groups and Teams deleted in the last 30 days.",
    "entra m365group recyclebinitem list --output text", []),
  T("Restore a deleted Microsoft 365 group",
    "Brings back a deleted group or Team (within 30 days), with its files and mail.",
    "entra m365group recyclebinitem restore --displayName {deleted}",
    [F("Display name of the deleted group", "deleted")]),
  T("List all Teams", "Every Microsoft Teams team in the organization.",
    "teams team list --output text", []),
  T("Teams a user is in", "The Teams one person is a direct member of.",
    "teams team list --joined --userName {email} --output text", [F("User (UPN)", "email")]),
  T("Get a Team's settings", "Shows one Team's settings (messaging, guests, fun settings...).",
    "teams team get --name {team} --output text", [F("Team display name", "team")]),
  T("Create a Team",
    "Creates a new Team (with its Microsoft 365 group and SharePoint site) and waits until "
    "it is ready. Owners / members: comma-separated sign-in names.",
    "teams team add --name {newteam} --description {desc} [--ownerUserNames {owners}] "
    "[--memberUserNames {members}] --wait",
    [F("Team name", "newteam"), F("Description", "desc"),
     F("Owners (UPNs, comma-separated, optional)", "owners", False),
     F("Members (UPNs, comma-separated, optional)", "members", False)]),
  T("Archive a Team",
    "Makes a Team read-only (e.g. a finished class or project). It can be restored with "
    "'Unarchive a Team'.", "teams team archive --name {team}", [F("Team display name", "team")]),
  T("Archive a Team and make its files read-only",
    "Archives the Team AND makes its SharePoint files read-only for members.",
    "teams team archive --name {team} --shouldSetSpoSiteReadOnlyForMembers",
    [F("Team display name", "team")]),
  T("Unarchive a Team", "Makes an archived Team active again.",
    "teams team unarchive --name {team}", [F("Team display name", "team")]),
  T("Delete a Team (DESTRUCTIVE)",
    "Deletes the Team, its group, files and conversations (recoverable for 30 days from "
    "'Deleted Microsoft 365 groups').",
    "teams team remove --name {team} --force", [F("Team display name", "team")], destructive=True),
  T("List a Team's channels", "The channels in one Team. Choose a type to see only those.",
    "teams channel list --teamName {team} [--type {ctype}] --output text",
    [F("Team display name", "team"),
     F("Only this type (blank = all)", "ctype", False, choices=["", "standard", "private", "shared"])]),
  T("Add a channel to a Team",
    "Adds a channel. A private or shared channel needs an owner.",
    "teams channel add --teamName {team} --name {channel} [--description {desc}] --type {ctype} "
    "[--owner {owner}]",
    [F("Team display name", "team"), F("Channel name", "channel"),
     F("Description (optional)", "desc", False),
     F("Type", "ctype", choices=["standard", "private", "shared"]),
     F("Owner (UPN) - needed for private / shared", "owner", False)]),
  T("Delete a channel (DESTRUCTIVE)", "Deletes a channel and its conversations.",
    "teams channel remove --teamName {team} --name {channel} --force",
    [F("Team display name", "team"), F("Channel name", "channel")], destructive=True),
  T("List a channel's members", "Who is in one channel. Choose a role to see only those.",
    "teams channel member list --teamName {team} --channelName {channel} [--role {crole}] --output text",
    [F("Team display name", "team"), F("Channel name", "channel"),
     F("Only this role (blank = all)", "crole", False, choices=["", "owner", "member", "guest"])]),
  # v0.12 (10-28-2026): options checked with the CLI's docs (v11.11) and run live.
  T("Apps installed in a Team",
    "The apps added to one Team (including the built-in ones such as Activity and Calling).",
    "teams team app list --teamName {team} --output text",
    [F("Team display name", "team")]),
  T("Teams apps in the organization's app catalog",
    "Apps people can add in Teams. 'organization' = apps your organization uploaded for "
    "everyone; 'store' = Microsoft's store (thousands of apps); blank = all. An empty "
    "result means there are none of that kind.",
    "teams app list [--distributionMethod {dist}] --output text",
    [F("Only these apps (blank = all)", "dist", False,
       choices=["organization", "sideloaded", "store", ""], default="organization")]),
  # v0.14 (10-29-2026): read-only, run live.
  T("Teams apps a person has installed",
    "The apps in one person's Teams (their personal apps, including the built-in ones).",
    "teams user app list --userName {email} --output text",
    [F("User (UPN)", "email")]),
 ],
 "Service health and security": [
  # v0.7 (10-23-2026): options checked against the CLI's docs.
  T("Service health right now", "The current health of every Microsoft 365 service.",
    "tenant serviceannouncement health list --output text", []),
  T("Current service issues", "Incidents and advisories Microsoft is working on. Name a "
    "service (e.g. Exchange Online) to see only its issues.",
    "tenant serviceannouncement healthissue list [--service {service}] --output text",
    [F("Only this service (optional) e.g. Microsoft Teams", "service", False)]),
  T("Message center updates", "Microsoft's announcements of upcoming changes.",
    "tenant serviceannouncement message list [--service {service}] --output text",
    [F("Only this service (optional) e.g. SharePoint Online", "service", False)]),
  T("Security alerts", "Security alerts raised for the organization.",
    "tenant security alerts list --output text", []),
  T("Organization info", "The tenant's ID, name and default domain.",
    "tenant info get --output text", []),
  T("Apps in the organization (enterprise apps)",
    "Every app that has access to the organization - review these regularly.",
    "entra enterpriseapp list --output text", []),
  T("What an app is allowed to do (permission grants)",
    "The permissions people consented to for one app. Get its object id from 'Apps in the "
    "organization'.", "entra oauth2grant list --spObjectId {id} --output text",
    [F("App's object id (service principal)", "id")]),
  # v0.14 (10-29-2026): read-only; options from the CLI's --help (v11.11), run live.
  T("App-only permissions granted to an app",
    "What one app may do on its own, without a signed-in person (application permissions "
    "such as reading every mailbox) - the most powerful kind. Use the app's display name "
    "from 'Apps in the organization'. An empty result means it has none.",
    "entra approleassignment list --appDisplayName {app} --output text",
    [F("App display name", "app")]),
  T("App registrations made in the organization",
    "The apps registered in this organization's own Microsoft Entra ID (scripts, "
    "integrations, tools such as this one), with when each was made and who can sign in "
    "to it.",
    "entra app list --properties \"displayName,appId,createdDateTime,signInAudience\" --output text",
    []),
  T("Permissions an app registration asks for",
    "The API permissions one app registration requests - delegated (acting as the "
    "signed-in person), application (acting on its own) or both. An empty result means "
    "it requests none.",
    "entra app permission list --appName {app} --type {ptype} --output text",
    [F("App registration display name", "app"),
     F("Which permissions", "ptype", choices=["all", "application", "delegated"], default="all")]),
  T("Group settings for the organization",
    "The organization-wide settings for Microsoft 365 groups (for example who may create "
    "groups, guest access, naming rules), if any were set. An empty result means the "
    "defaults are used.",
    "entra groupsetting list --output text", []),
  T("Are names hidden in usage reports?",
    "Whether usage reports show people's names or hide them (Microsoft 365 admin center > "
    "Settings > Org settings > Reports).",
    "tenant report settings get --output text", []),
  T("Pronouns setting",
    "Whether people in the organization can add pronouns to their profile.",
    "tenant people pronouns get --output text", []),
  T("Search the audit log",
    "Audit records of one kind (sign-ins and directory changes, Exchange, SharePoint...). "
    "Dates like 2026-10-01. Needs audit logging switched on.",
    "purview auditlog list --contentType {ctype} [--startTime {start}] [--endTime {end}] --output text",
    [F("Kind of records", "ctype", choices=["AzureActiveDirectory", "Exchange", "SharePoint", "General", "DLP"]),
     F("From (optional) e.g. 2026-10-01", "start", False), F("Until (optional)", "end", False)]),
  T("Retention labels", "The retention labels defined in Purview.",
    "purview retentionlabel list --output text", []),
  T("Sensitivity labels", "The sensitivity labels defined in Purview. 'The resource could "
    "not be found' means the organization has none, or its licenses do not include "
    "them (Microsoft Purview Information Protection).",
    "purview sensitivitylabel list --output text", []),
 ],
 "Outlook": [
  # v0.7 (10-23-2026): options checked against the CLI's docs.
  T("Send an email",
    "Sends a plain-text email FROM YOUR account (the one m365 is signed in as).",
    "outlook mail send --to {to} --subject {subject} --bodyContents {body} [--cc {cc}]",
    [F("To (addresses, comma-separated)", "to"), F("Subject", "subject"), F("Message", "body"),
     F("Cc (optional)", "cc", False)],
    destructive=True),                     # a sent email cannot be taken back: confirm first
  T("A user's mailbox settings", "Automatic replies, time zone, language and working hours.",
    "outlook mailbox settings get --userName {email} --output text", [F("User (UPN)", "email")]),
  # v0.12 (10-27-2026): checked against 'm365 outlook ... --help full' on
  # CLI v11.11 (event list uses the default calendar when none is named;
  # autoReplyStatus disabled|alwaysEnabled|scheduled; autoReplyExternal-
  # Audience none|contactsOnly|all; date-times like 2025-01-06T11:00:00
  # with a time zone name).
  T("A user's calendars", "Every calendar in one user's mailbox (name, color, default).",
    "outlook calendar list --userName {email} --output text", [F("User (UPN)", "email")]),
  T("A user's calendar events",
    "Events in one user's default calendar. Give a date range (YYYY-MM-DD) to see only those days.",
    "outlook event list --userName {email} [--startDateTime {start}] [--endDateTime {end}] "
    "--properties \"subject,start,end,organizer,isCancelled\" --output text",
    [F("User (UPN)", "email"), F("From date (optional, YYYY-MM-DD)", "start", False),
     F("To date (optional, YYYY-MM-DD)", "end", False)]),
  T("Messages in a user's mail folder",
    "The messages in one folder of a user's mailbox (e.g. inbox, sentitems, deleteditems, "
    "archive). Needs Mail.Read for that mailbox.",
    "outlook message list --userName {email} --folderName {folder} --output text",
    [F("User (UPN)", "email"),
     F("Folder", "folder", choices=["inbox", "sentitems", "drafts", "deleteditems", "archive",
                                    "junkemail"], default="inbox")]),
  T("Turn on automatic replies (until turned off)",
    "Out of office for a user, starting now, until someone turns it off. The internal "
    "message goes to people in your organization; choose who outside it gets the external one.",
    "outlook mailbox settings set --userName {email} --autoReplyStatus alwaysEnabled "
    "--autoReplyInternalMessage {internal} --autoReplyExternalAudience {audience} "
    "[--autoReplyExternalMessage {external}]",
    [F("User (UPN)", "email"), F("Message to people in your organization", "internal"),
     F("Who outside the organization gets a reply", "audience",
       choices=["none", "contactsOnly", "all"], default="none"),
     F("Message to people outside (optional)", "external", False)],
    destructive=True),
  T("Turn on automatic replies for dates (scheduled)",
    "Out of office between two dates and times, in the time zone you name (a Windows time "
    "zone name such as Central Standard Time, or an IANA name such as America/Chicago).",
    "outlook mailbox settings set --userName {email} --autoReplyStatus scheduled "
    "--autoReplyStartDateTime {start} --autoReplyStartTimeZone {tz} "
    "--autoReplyEndDateTime {end} --autoReplyEndTimeZone {tz} "
    "--autoReplyInternalMessage {internal} --autoReplyExternalAudience {audience} "
    "[--autoReplyExternalMessage {external}]",
    [F("User (UPN)", "email"),
     F("Start - date and time (e.g. 2026-11-02T08:00:00)", "start"),
     F("End - date and time (e.g. 2026-11-06T17:00:00)", "end"),
     F("Time zone (e.g. Central Standard Time)", "tz"),
     F("Message to people in your organization", "internal"),
     F("Who outside the organization gets a reply", "audience",
       choices=["none", "contactsOnly", "all"], default="none"),
     F("Message to people outside (optional)", "external", False)],
    destructive=True),
  T("Turn off automatic replies", "Stops a user's out-of-office replies.",
    "outlook mailbox settings set --userName {email} --autoReplyStatus disabled",
    [F("User (UPN)", "email")], destructive=True),
  T("Meeting rooms", "Every room mailbox.", "outlook room list --output text", []),
  T("Room lists (buildings)", "The room lists rooms are grouped in.",
    "outlook roomlist list --output text", []),
 ],
 "Planner": [
  # v0.7 (10-23-2026): options checked against the CLI's docs.
  T("A group's plans", "The Planner plans of a Team / Microsoft 365 group.",
    "planner plan list --ownerGroupName {team} --output text",
    [F("Team / group display name", "team")]),
  T("Tasks in a plan", "Every task in one plan.",
    "planner task list --planTitle {plan} --ownerGroupName {team} --output text",
    [F("Plan title", "plan"), F("Team / group display name", "team")]),
 ],
 "Reports (usage)": [
  # v0.7 (10-23-2026): Microsoft 365 usage reports. Options checked against
  # the CLI's docs. Needs the Reports.Read.All permission; names may show as
  # IDs if the tenant hides user details in reports (admin center setting).
  # v0.10: was 'tenant report activeusercounts' - Microsoft Graph reset the
  # connection every time on a real tenant (10-26-2026, csv and json, every
  # period) while the other reports worked; servicesusercounts answers the
  # same question and works.
  T("Active users per service (counts)",
    "How many people were active and inactive in each Microsoft 365 service.",
    "tenant report servicesusercounts --period {period} --output csv",
    [F("Period", "period", choices=["D7", "D30", "D90", "D180"], default="D30")]),
  T("Active users - per person", "Each person's last activity date in each service.",
    "tenant report activeuserdetail --period {period} --output csv",
    [F("Period", "period", choices=["D7", "D30", "D90", "D180"], default="D30")]),
  T("Teams activity - per person", "Chats, meetings and calls per person.",
    "teams report useractivityuserdetail --period {period} --output csv",
    [F("Period", "period", choices=["D7", "D30", "D90", "D180"], default="D30")]),
  T("Teams devices used - per person", "Which devices (Windows, Mac, iOS, Android, web) people use Teams on.",
    "teams report deviceusageuserdetail --period {period} --output csv",
    [F("Period", "period", choices=["D7", "D30", "D90", "D180"], default="D30")]),
  T("OneDrive storage - per account", "Files and storage used in each OneDrive.",
    "onedrive report usageaccountdetail --period {period} --output csv",
    [F("Period", "period", choices=["D7", "D30", "D90", "D180"], default="D30")]),
  T("OneDrive activity - per person", "Files viewed, edited, synced and shared per person.",
    "onedrive report activityuserdetail --period {period} --output csv",
    [F("Period", "period", choices=["D7", "D30", "D90", "D180"], default="D30")]),
  T("Mailbox storage - per mailbox", "Size and item counts of every mailbox.",
    "outlook report mailboxusagedetail --period {period} --output csv",
    [F("Period", "period", choices=["D7", "D30", "D90", "D180"], default="D30")]),
  T("Email activity - per person", "Mail sent, received and read per person.",
    "outlook report mailactivityuserdetail --period {period} --output csv",
    [F("Period", "period", choices=["D7", "D30", "D90", "D180"], default="D30")]),
  T("SharePoint site usage - per site", "Files, storage and activity of each SharePoint site.",
    "spo report siteusagedetail --period {period} --output csv",
    [F("Period", "period", choices=["D7", "D30", "D90", "D180"], default="D30")]),
  # v0.12 (10-28-2026): checked with the CLI's docs and run live.
  T("Mailboxes near their size limit (counts)",
    "For each day: how many mailboxes are under the limit, were warned, or can no longer "
    "send / receive.",
    "outlook report mailboxusagequotastatusmailboxcounts --period {period} --output csv",
    [F("Period", "period", choices=["D7", "D30", "D90", "D180"], default="D30")]),
  T("OneDrive storage used - whole organization",
    "Total OneDrive storage used each day (bytes).",
    "onedrive report usagestorage --period {period} --output csv",
    [F("Period", "period", choices=["D7", "D30", "D90", "D180"], default="D30")]),
 ],
 "Roles and admin units": [
  # ---- v0.13 (10-28-2026): guided, read-only (m365_workflows.admin_roles) ----
  T("Who holds admin roles",
    "Every person and app that holds a Microsoft Entra admin role, by role - Global "
    "Administrators first - and what is worth a second look: too many or too few Global "
    "Administrators, an account with many roles, a blocked account that still holds one, "
    "and (v0.14) anyone with a role who has NO MFA method registered or has not "
    "signed in for the days you choose. "
    "Changes nothing; a CSV is saved in the Records folder. Works without Entra ID P2 "
    "(reads Microsoft Graph); needs RoleManagement.Read.Directory or Directory.Read.All, "
    "and AuditLog.Read.All (with Entra ID P1 or P2) for the MFA and sign-in checks.",
    "", [F("Include apps (service principals)", "apps", choices=["Yes", "No"], default="Yes"),
         F("Point out people who have not signed in for (days)", "days", False, default="90")],
    workflow="admin_roles"),
  # v0.7 (10-23-2026): options checked against the CLI's docs.
  T("List admin roles", "Every Microsoft Entra admin role (Global Administrator, User "
    "Administrator...).", "entra roledefinition list --output text", []),
  T("Give someone an admin role (whole organization)",
    "Assigns an Entra admin role, e.g. 'Helpdesk Administrator', to a user. Get the exact "
    "name from 'List admin roles'.",
    "entra roleassignment add --roleDefinitionName {role} --principal {email}",
    [F("Role name e.g. Helpdesk Administrator", "role"), F("User (UPN)", "email")],
    destructive=True),
  T("List administrative units", "Administrative units (e.g. one per campus) used to limit "
    "what delegated admins can manage.", "entra administrativeunit list --output text", []),
  T("Members of an administrative unit",
    "Lists the users, groups or devices in one administrative unit.",
    "entra administrativeunit member list --administrativeUnitName {au} [--type {type}] --output text",
    [F("Administrative unit name", "au"),
     F("Only this kind (blank = all)", "type", False, choices=["", "user", "group", "device"])]),
  T("Add a user to an administrative unit", "Puts a user under an administrative unit.",
    "entra administrativeunit member add --administrativeUnitName {au} --userName {email}",
    [F("Administrative unit name", "au"), F("User (UPN)", "email")]),
 ],
 "SharePoint": [
  T("List sites", "Lists SharePoint sites in the tenant.",
    "spo site list --output text", []),
  T("Add user to a SharePoint group",
    "Adds a user to a SharePoint group on a specific site.",
    "spo group member add --webUrl {url} --groupName {group} --userNames {email}",
    [F("Site URL e.g. https://contoso.sharepoint.com/sites/Team", "url"),
     F("SharePoint group name", "group"), F("User (UPN)", "email")]),
  # ---- v0.7 (10-23-2026): options checked against the CLI's docs ----------
  T("List team or communication sites", "Only one kind of modern site.",
    "spo site list --type {stype} --output text",
    [F("Kind of site", "stype", choices=["TeamSite", "CommunicationSite"])]),
  T("List every site, OneDrives included", "All sites plus every person's OneDrive.",
    "spo site list --withOneDriveSites --output text", []),
  T("Get a site's info", "Owner, storage, sharing and lock state of one site.",
    "spo site get --url {url} --output text",
    [F("Site URL e.g. https://contoso.sharepoint.com/sites/Team", "url")]),
  T("Create a team site",
    "A team site with its own Microsoft 365 group. The alias becomes part of the address "
    "and the group's email.",
    "spo site add --type TeamSite --title {title} --alias {alias} [--description {desc}] [--owners {owners}]",
    [F("Site title", "title"), F("Alias e.g. hr-team", "alias"),
     F("Description (optional)", "desc", False),
     F("Owners (UPNs, comma-separated, optional)", "owners", False)]),
  T("Create a communication site",
    "A site for publishing to many people (no group).",
    "spo site add --type CommunicationSite --title {title} --url {url} [--description {desc}]",
    [F("Site title", "title"), F("Site URL e.g. https://contoso.sharepoint.com/sites/News", "url"),
     F("Description (optional)", "desc", False)]),
  T("Delete a site (DESTRUCTIVE)",
    "Deletes a site - it goes to the SharePoint recycle bin for 93 days ('Deleted sites').",
    "spo site remove --url {url} --force",
    [F("Site URL", "url")], destructive=True),
  T("Deleted sites (recycle bin)", "Sites deleted in the last 93 days.",
    "spo tenant recyclebinitem list --output text", []),
  T("Restore a deleted site", "Brings a deleted site back from the recycle bin.",
    "spo tenant recyclebinitem restore --siteUrl {url}", [F("Site URL", "url")]),
  T("Site collection admins of a site", "Who has full control of a site.",
    "spo site admin list --siteUrl {url} --asAdmin --output text", [F("Site URL", "url")]),
  T("Add a site collection admin", "Gives a user full control of a site.",
    "spo site admin add --siteUrl {url} --userName {email} --asAdmin",
    [F("Site URL", "url"), F("User (UPN)", "email")]),
  T("Remove a site collection admin (DESTRUCTIVE)", "Takes a user's full control of a site away.",
    "spo site admin remove --siteUrl {url} --userName {email} --asAdmin --force",
    [F("Site URL", "url"), F("User (UPN)", "email")], destructive=True),
  T("Lock a site or make it read-only",
    "NoAdditions = no new content; ReadOnly = nothing can change; NoAccess = nobody can open "
    "it; Unlock = back to normal.",
    "spo site set --url {url} --lockState {lock}",
    [F("Site URL", "url"), F("Lock state", "lock", choices=["ReadOnly", "NoAdditions", "NoAccess", "Unlock"])],
    destructive=True),
  T("Change who a site can be shared with",
    "Disabled = only people in the organization; the others allow guests (new or existing).",
    "spo site set --url {url} --sharingCapability {share}",
    [F("Site URL", "url"),
     F("Sharing", "share", choices=["Disabled", "ExistingExternalUserSharingOnly",
                                     "ExternalUserSharingOnly", "ExternalUserAndGuestSharing"])]),
  T("A site's recycle bin", "Deleted files, folders and list items of one site.",
    "spo site recyclebinitem list --siteUrl {url} [--type {rtype}] --output text",
    [F("Site URL", "url"),
     F("Only this kind (blank = all)", "rtype", False, choices=["", "files", "folders", "listItems"])]),
  T("Restore everything in a site's recycle bin",
    "Restores every item in the site's (first-stage) recycle bin.",
    "spo site recyclebinitem restore --siteUrl {url} --allPrimary", [F("Site URL", "url")]),
  T("External (guest) users files were shared with",
    "People outside the organization who were given access - for every site, or one.",
    "spo externaluser list [--siteUrl {url}] --output text",
    [F("Only this site (optional)", "url", False)]),
  T("SharePoint organization settings", "The SharePoint / OneDrive settings for the whole organization.",
    "spo tenant settings list --output text", []),
  # v0.14 (10-29-2026): read-only; options checked with the CLI's --help
  # (v11.11) and every command run live. A library's 'Forms' folder holds
  # SharePoint's own .aspx pages, so they show up in file lists.
  T("SharePoint groups on a site",
    "The SharePoint groups of one site (usually its Owners, Members and Visitors groups). "
    "Use 'Members of a SharePoint group' to see who is in one.",
    "spo group list --webUrl {url} --output text",
    [F("Site URL e.g. https://contoso.sharepoint.com/sites/Team", "url")]),
  T("Members of a SharePoint group",
    "Who is in one SharePoint group on a site. The group name is shown by 'SharePoint groups "
    "on a site'.",
    "spo group member list --webUrl {url} --groupName {group} --output text",
    [F("Site URL e.g. https://contoso.sharepoint.com/sites/Team", "url"),
     F("SharePoint group name e.g. Team Members", "group")]),
  T("Lists and libraries on a site",
    "The lists and document libraries people can see on one site (SharePoint's hidden "
    "system lists are left out).",
    "spo list list --webUrl {url} --filter \"Hidden eq false\" --output text",
    [F("Site URL e.g. https://contoso.sharepoint.com/sites/Team", "url")]),
  T("Files in a folder",
    "The files directly in one folder of a site (not in its subfolders). The folder is "
    "relative to the site, e.g. 'Shared Documents' or 'Shared Documents/Reports'. For a "
    "OneDrive, use its address as the site and 'Documents' as the folder.",
    "spo file list --webUrl {url} --folderUrl {folder} --output text",
    [F("Site URL e.g. https://contoso.sharepoint.com/sites/Team", "url"),
     F("Folder e.g. Shared Documents", "folder", default="Shared Documents")]),
  T("Every file in a folder, subfolders included",
    "Every file in a folder and all of its subfolders. A big library or OneDrive can take "
    "many minutes.",
    "spo file list --webUrl {url} --folderUrl {folder} --recursive --output text",
    [F("Site URL e.g. https://contoso.sharepoint.com/sites/Team", "url"),
     F("Folder e.g. Shared Documents", "folder", default="Shared Documents")]),
  T("Sharing links on a file",
    "The sharing links made for one file. 'anonymous' = anyone with the link, 'users' = "
    "specific people, 'organization' = everyone in the organization; blank = all. An "
    "empty result means the file has no links of that kind.",
    "spo file sharinglink list --webUrl {url} --fileUrl {file} [--scope {scope}] --output text",
    [F("Site URL e.g. https://contoso.sharepoint.com/sites/Team", "url"),
     F("File e.g. /sites/Team/Shared Documents/report.docx", "file"),
     F("Only this kind of link (blank = all)", "scope", False,
       choices=["", "anonymous", "users", "organization"])]),
  T("Who can open a file (sharing details)",
    "Everyone who can open one file and how: sharing links (with who used them), people "
    "and groups given access, and the site admins. Shown as JSON - the CLI gives these "
    "details only in that form.",
    "spo file sharinginfo get --webUrl {url} --fileUrl {file} --output json",
    [F("Site URL e.g. https://contoso.sharepoint.com/sites/Team", "url"),
     F("File e.g. /sites/Team/Shared Documents/report.docx", "file")]),
  T("Hub sites",
    "The organization's hub sites (sites that join other sites together). An empty "
    "result means there are none.",
    "spo hubsite list --output text", []),
  # ---- v0.14: guided, read-only (m365_workflows.shared_links) ----------------
  T("Files shared by link in a folder",
    "Checks every file in one folder of a site (and its subfolders) for sharing links - "
    "by default only 'anyone with the link' links, which open the file without signing "
    "in - and points out the ones that allow editing or never expire. Changes nothing; a "
    "CSV is saved in the Records folder (without the link addresses). One check per file, "
    "so a big library takes a while.",
    "", [F("Site URL e.g. https://contoso.sharepoint.com/sites/Team", "url"),
         F("Folder e.g. Shared Documents", "folder", default="Shared Documents"),
         F("Include subfolders", "subfolders", choices=["Yes", "No"], default="Yes"),
         F("Which links", "kind", choices=[SHARE_ANYONE, SHARE_ALL], default=SHARE_ANYONE)],
    workflow="shared_links"),
 ],
 "Security": [
  # ---- v0.14: guided, read-only (m365_workflows.conditional_access) ----------
  T("Conditional Access review",
    "Every Conditional Access policy in plain words - what it requires (MFA, a compliant "
    "device, block...), who it applies to and who is excluded, by name - and what is worth "
    "a second look: no policy that is ON requires MFA for everyone or for Global "
    "Administrators, nothing blocks legacy authentication, and who is excluded from "
    "policies that are ON. Changes nothing; a CSV is saved in the Records folder. Needs "
    "Policy.Read.All (Conditional Access needs Microsoft Entra ID P1 or P2).",
    "", [], workflow="conditional_access"),
  # ---- v0.8: guided workflow (m365_workflows.compromised_response) ----------
  T("Compromised account response",
    "For an account someone else got into: blocks sign-in, signs it out everywhere and sets "
    "a new random password (shown once, never saved), then saves evidence - recent "
    "sign-ins, MFA methods, groups, licenses - and a list of the next steps to do in the "
    "admin centers. Asks once before changing anything.",
    "", [F("User (UPN)", "email"),
         F("Block sign-in", "block", choices=["Yes", "No"], default="Yes"),
         F("Sign them out everywhere", "signout", choices=["Yes", "No"], default="Yes"),
         F("Set a new random password", "password", choices=["Yes", "No"], default="Yes")],
    workflow="compromised"),
  T("Sign user out everywhere",
    "Revokes all sign-in sessions for the user - first move on a compromised "
    "account (they must sign in again).",
    "entra user session revoke --userName {email} --force",
    [F("User (UPN)", "email")], destructive=True),
  T("Sign-in activity",
    "Lists recent sign-ins for a user. REQUIRES the AuditLog.Read.All Graph "
    "permission AND a Microsoft Entra ID P1/P2 (premium) tenant - sign-in logs "
    "are a premium feature. If it fails with 'Error: [object Object]', that is "
    "the CLI hiding the real message; re-run the command with --debug (or add "
    "--verbose in Custom command) to see the actual reason.",
    "entra user signin list --userName {email} --output text",
    [F("User (UPN)", "email")]),
  # v0.12 (10-28-2026): options checked with the CLI's docs (v11.11) and every
  # listed type run live (read-only). Shown as JSON: policies are nested and
  # the text output shows only their names. The type is required: without
  # one the CLI also reads 'roleManagement', which needs Entra ID P2 and
  # fails the whole command on other tenants (seen live 10-28-2026).
  T("Microsoft Entra policies (settings)",
    "Shows one kind of Entra policy: who may invite guests or register apps "
    "(authorization), security defaults, sign-in methods, Conditional Access, "
    "device registration and more. Needs the Policy.Read.All permission.",
    "entra policy list --type {ptype}",
    [F("Policy type", "ptype",
       choices=["authorization", "identitySecurityDefaultsEnforcement",
                "authenticationMethods", "authenticationStrength", "authenticationFlows",
                "conditionalAccess", "deviceRegistration", "adminConsentRequest",
                "permissionGrant", "activityBasedTimeout", "tokenLifetime",
                "crossTenantAccess"], default="authorization")]),
 ],
 "OneDrive": [
  T("List every OneDrive",
    "Every person's OneDrive, with its owner, size and address (SharePoint administrator).",
    "onedrive list --output text", []),
  T("Find a user's OneDrive address",
    "Shows the web address of a user's OneDrive (empty if their OneDrive has "
    "never been set up - it is created the first time they open it).",
    "entra user get --userName {email} --properties userPrincipalName,mySite --output text",
    [F("User (UPN)", "email")]),
  T("Copy a user's OneDrive files to another user",
    "For a person who is leaving: copies EVERYTHING in their OneDrive into a "
    "new folder in another person's OneDrive (e.g. their manager). Nothing "
    "is removed from the original owner, and files with the same name are "
    "renamed, never overwritten. Shows the file count and asks before "
    "copying; afterwards counts the files that arrived and saves a CSV "
    "record in the Logs folder. You need to be a SharePoint or Global "
    "administrator: M365GUI gives you access to both OneDrives for the copy "
    "and takes it away again afterwards (unless you choose to keep it).",
    "", [F("From: whose files (UPN) e.g. jdoe@contoso.com", "from"),
         F("To: who gets a copy (UPN) e.g. manager@contoso.com", "to"),
         F("Folder name in their OneDrive (optional - default 'Files from <name> <date>')",
           "folder", False),
         F("Afterwards", "access", choices=[TRANSFER_ACCESS_REMOVE, TRANSFER_ACCESS_KEEP])],
    workflow="onedrive_transfer"),
 ],
 "Diagnostics": [
  T("Login status", "Shows whether the CLI is signed in and to which tenant.",
    "status", []),
  T("CLI version", "Shows the CLI for Microsoft 365 version.", "version", []),
  T("Tenant ID", "Shows the tenant's directory (tenant) id.",
    "tenant id get", []),
  # v0.12 (10-28-2026): checked with the CLI's docs and run live.
  T("Organization (tenant) details",
    "The organization's name, tenant id and type, and when directory sync (Entra Connect) "
    "last ran. Blank values are not shown.",
    "entra organization list --properties displayName,id,tenantType,countryLetterCode,"
    "onPremisesSyncEnabled,onPremisesLastSyncDateTime --output text", []),
  # v0.11 - connections (like GAMGUI's Section dropdown): each 'm365 login'
  # adds a connection; 'connection use' picks the one EVERY command uses. The
  # Connection list at the top of the window switches too.
  T("List saved connections (accounts / tenants)",
    "Lists every account the CLI is signed in with (a 'connection' each) and "
    "which one is active. The Connection list at the top of the window "
    "switches between them.",
    "connection list --output text", []),
  T("Switch to another connection",
    "Makes another saved connection the active one: every command after this "
    "runs as that account, in its tenant. Same as choosing it in the "
    "Connection list at the top of the window.",
    "connection use --name {connection}",
    [F("Connection name or ID (see List saved connections)", "connection")]),
  T("Rename a connection",
    "Gives a saved connection an easy name (e.g. 'school' or 'test tenant') "
    "instead of its long ID.",
    "connection set --name {connection} --newName {newname}",
    [F("Connection name or ID (see List saved connections)", "connection"),
     F("New name", "newname")]),
  T("Remove a saved connection",
    "Forgets a saved connection and its sign-in on this computer. Nothing "
    "changes in Microsoft 365; sign in again to get it back.",
    "connection remove --name {connection} --force",
    [F("Connection name or ID (see List saved connections)", "connection")],
    destructive=True),
  T("Sign in another account (adds a connection)",
    "Signs the CLI in with another account or tenant and keeps the current "
    "one as a saved connection. 'deviceCode': a web address and a code appear "
    "in the output - open the address on any device, type the code and sign "
    "in; 'browser': a sign-in page opens in this computer's web browser. The "
    "new connection becomes the active one.",
    "login --authType {authtype} [--connectionName {connname}]",
    [F("How to sign in", "authtype", choices=["deviceCode", "browser"]),
     F("Name for the new connection (optional) e.g. school", "connname", False)]),
  T("Sign out",
    "Signs the CLI out of Microsoft 365 and removes its sign-in tokens from "
    "this computer. Run 'Sign in another account' (or 'm365 login') to sign "
    "in again.",
    "logout", [], destructive=True),
 ],
}

# What the preview box says for a guided workflow (it runs several commands).
WORKFLOW_PLANS = {
    "remove_guests": "Workflow: list guests -> confirm (type DELETE) -> remove each. "
                     "Click Run to start.",
    "onedrive_transfer": "Workflow: find both OneDrives -> give you temporary access -> "
                         "count the files -> ask you -> copy into the new folder -> "
                         "count what arrived -> remove the temporary access. Click Run "
                         "to start.",
    "staff_handoff": "Workflow: save a record of their groups and licenses -> ask you -> "
                     "block sign-in -> sign out -> copy OneDrive files -> automatic reply "
                     "-> remove from groups -> remove licenses (only the steps set to Yes). "
                     "Records in the Records folder. Click Run to start.",
    "compromised": "Workflow: ask you -> block sign-in -> sign out everywhere -> new random "
                   "password (shown once) -> save evidence (sign-ins, MFA methods, groups, "
                   "licenses) and NEXT-STEPS.txt in the Records folder. Click Run to start.",
    "admin_roles": "Workflow (read-only): read every admin role assignment from Microsoft "
                   "Graph -> look up the role names -> read each person's MFA registration "
                   "-> list them by role with notes -> save "
                   "admin-roles.csv in the Records folder. Nothing is changed. Click Run to "
                   "start.",
    "conditional_access": "Workflow (read-only): read every Conditional Access policy from "
                          "Microsoft Graph -> look up the role, user and group names -> "
                          "describe each policy with notes -> save conditional-access.csv in "
                          "the Records folder. Nothing is changed. Click Run to start.",
    "shared_links": "Workflow (read-only): list the files in the folder (and subfolders) -> "
                    "read each file's sharing links -> list them with notes -> save "
                    "shared-links.csv in the Records folder (no link addresses). Nothing is "
                    "changed. Click Run to start.",
}

# =============================================================================
# SECTION: Command building (same engine as GAMGUI)
# =============================================================================

def quote_if_needed(value):
    value = value.strip()
    if value.startswith('"') and value.endswith('"') and len(value) > 1:
        return value
    if " " in value or '"' in value:
        return '"' + value.replace('"', '\\"') + '"'
    return value

def build_command(task, values, category=""):
    # v0.6: pasted curly quotes / invisible characters in address and ID
    # boxes are removed first (clean_identifier_values, as in GAMGUI 2.93).
    values = clean_identifier_values(task, values, category)
    template = task["template"]

    def seg_sub(match):
        segment = match.group(0)[1:-1]
        keys = re.findall(r"{(\w+)[^}]*}", segment)
        if any(values.get(k, "").strip() for k in keys):
            return segment
        return ""
    # Optional segments are flag groups like [--usageLocation {loc}]. The
    # pattern requires the segment to begin with "--" so it does NOT collide
    # with literal JMESPath brackets in a --query value, e.g.
    # [?assignedLicenses[?skuId=='...']].
    rendered = re.sub(r"\[--[^\]]*\]", seg_sub, template)

    argv, display_parts, problem = [], [], [""]

    def fill(m):
        key, fallback = m.group(1), m.group(2) or ""
        v = values.get(key, "").strip()
        if not v:
            if fallback:
                v = fallback
            else:
                problem[0] = "Missing required value: " + key
        return v

    # Split on whitespace but keep quoted "..." segments together so that
    # options like --properties "a,b,c" stay a single argument.
    for token in re.findall(r'"[^"]*"|\S+', rendered):
        filled = re.sub(r"{(\w+)(?:\|([^}]*))?}", fill, token)
        if problem[0]:
            return "", [], problem[0]
        if filled.startswith('"') and filled.endswith('"') and len(filled) > 1:
            inner = filled[1:-1]
            argv.append(inner)
            display_parts.append(quote_if_needed(inner))
        else:
            argv.append(filled)
            display_parts.append(quote_if_needed(filled))
    return " ".join(display_parts), argv, ""


# =============================================================================
# SECTION: Finding tasks - search box, Favorites and Recent (v0.6, as GAMGUI)
# =============================================================================

def is_identifier_field(category, task, field):
    # True for a box that holds an address / ID (cleaned before building).
    if field["key"] in NEVER_CLEAN_KEYS or field.get("choices") is not None:
        return False
    return field["key"] in IDENTIFIER_KEYS or bool(picker_kind(category, task, field))

def _clean_item(item):
    # The spaces before an item stay (they follow a comma), but not a
    # non-breaking space (chr 0xA0) - that is pasted junk wherever it sits.
    lead = item[:len(item) - len(item.lstrip())].replace(chr(0xa0), "")
    core = item.strip().replace("\u00a0", " ").strip()
    while len(core) >= 2 and core[0] in _WRAP_QUOTES and core[-1] in _WRAP_QUOTES:
        core = core[1:-1].strip()
    return lead + core

def clean_identifier(value):
    # Drops invisible zero-width characters anywhere; then, for each comma-
    # separated item, non-breaking spaces at its ends and quotes (straight or
    # curly) wrapped around the whole item. Separators and inner text stay.
    text = _ZERO_WIDTH.sub("", str(value or ""))
    return re.sub(r"[^,]+", lambda m: _clean_item(m.group(0)), text)

def clean_identifier_values(task, values, category=""):
    # The form's values with every identifier box cleaned (see above).
    out = dict(values)
    for field in (task or {}).get("fields", []):
        key = field["key"]
        if key in out and isinstance(out[key], str) and is_identifier_field(category, task, field):
            out[key] = clean_identifier(out[key])
    return out

# ---- "Save results to" (v0.6, as GAMGUI's Screen / CSV file choice) ----------
SAVE_CHOICES = ["Screen", "CSV file", "JSON file"]
SAVE_FORMATS = {"CSV file": "csv", "JSON file": "json"}

def saves_output(task):
    # A task that prints a list or details ('--output text' in its
    # template) can send them to a file instead.
    # v0.10: or '--output csv' - the usage reports (the CLI refuses text there).
    template = task.get("template", "")
    return not task.get("workflow") and ("--output text" in template or "--output csv" in template)

def with_output_format(argv, fmt):
    # The same command with its --output value changed (added if missing);
    # the CLI itself writes the CSV / JSON (m365 global option --output).
    argv = list(argv)
    for i, arg in enumerate(argv[:-1]):
        if arg in ("--output", "-o"):
            argv[i + 1] = fmt
            return argv
    return argv + ["--output", fmt]

def dropdown_start(field):
    # What a dropdown starts on (GAMGUI 2.91's rule): its default when that
    # is one of the choices, else the first choice.
    choices = field.get("choices") or []
    default = field.get("default") or ""
    return default if default in choices else (choices[0] if choices else default)

# ---- "Run for each CSV row" (v0.6, as GAMGUI's bulk runs) ---------------------
# The m365 CLI has no CSV loop (GAM has 'gam csv'), so M365GUI runs the task
# once per row itself. Each form box takes its value from a CSV column or
# from the form.
FORM_VALUE = "(the value in the form)"

def bulk_available(task):
    # Ordinary command tasks with at least one box; not the guided workflows.
    return bool(task.get("template")) and not task.get("workflow") and bool(task.get("fields"))

def bulk_guess_column(field, headers):
    # The column a box most likely reads from: its key, or a column named
    # like it (userPrincipalName for a UPN box...). FORM_VALUE when unsure.
    lowered = {h.lower(): h for h in headers}
    wanted = [field["key"].lower()]
    if field["key"] in USER_PICK_KEYS:
        wanted += ["userprincipalname", "upn", "email", "mail", "user"]
    if field["key"] in ("name", "team", "group"):
        wanted += ["displayname", "groupname", "group", "name"]
    if field["key"] == "id":
        wanted += ["id", "objectid"]
    for w in wanted:
        if w in lowered:
            return lowered[w]
    return FORM_VALUE

def bulk_plan(task, category, form_values, mapping, rows):
    # One entry per CSV row: (row number, argv, error). mapping[key] is a
    # column name or FORM_VALUE. Row numbers count the header as row 1, as
    # a spreadsheet shows them.
    plan = []
    for number, row in enumerate(rows, start=2):
        values = dict(form_values)
        for key, column in mapping.items():
            if column != FORM_VALUE:
                values[key] = (row.get(column) or "").strip()
        _display, argv, err = build_command(task, values, category)
        plan.append((number, argv, err))
    return plan

# ---- "Save as script" (v0.6, as GAMGUI) ---------------------------------------
# PowerShell (.ps1) and bash (.sh) only: both can quote ANY value safely
# (single quotes). A .bat would go through cmd.exe, which treats & | < > ^ %
# inside a value as commands - the problem M365GUI 0.4 removed.

def ps_quote(arg):
    # PowerShell single-quoted string: nothing inside is special except ',
    # which is doubled.
    return "'" + str(arg).replace("'", "''") + "'"

def sh_quote(arg):
    # bash single-quoted string; a ' is closed, escaped and reopened.
    return "'" + str(arg).replace("'", "'\\''") + "'"

def script_text(argv, kind, task_name, app_version, date_text):
    # The whole script for one m365 command. kind: "ps1" or "sh".
    title = (task_name or "Custom command").replace("\r", " ").replace("\n", " ")
    if kind == "ps1":
        # Windows PowerShell 5.1 drops a double quote INSIDE a value it hands
        # to a program (checked 10-23-2026: 'a "HQ"' arrived as 'a HQ');
        # PowerShell 7.3+ passes values exactly when told to ('Standard').
        # So the script refuses to run such a value under 5.1 instead of
        # silently changing it.
        return ("# %s - saved from M365GUI %s on %s\r\n"
                "# Runs one CLI for Microsoft 365 command. Needs m365 installed and signed in\r\n"
                "# ('m365 login'). Run: powershell -ExecutionPolicy Bypass -File <this file>\r\n"
                "$ErrorActionPreference = 'Stop'\r\n"
                "$arguments = @(%s)\r\n"
                "if ($PSVersionTable.PSVersion -lt [version]'7.3' -and ($arguments -match '\"')) {\r\n"
                "    Write-Error ('A value contains a double quote, which Windows PowerShell 5.1 cannot pass ' +\r\n"
                "                 'to m365 unchanged. Run this script with PowerShell 7 (pwsh) instead.')\r\n"
                "    exit 1\r\n"
                "}\r\n"
                "$PSNativeCommandArgumentPassing = 'Standard'\r\n"
                "& m365 @arguments\r\n"
                "if ($LASTEXITCODE -ne 0) { Write-Error ('m365 failed with exit code ' + $LASTEXITCODE); exit $LASTEXITCODE }\r\n"
                % (title, app_version, date_text, ", ".join(ps_quote(a) for a in argv)))
    return ("#!/usr/bin/env bash\n"
            "# %s - saved from M365GUI %s on %s\n"
            "# Runs one CLI for Microsoft 365 command. Needs m365 installed and signed in\n"
            "# ('m365 login'). Run: bash <this file>\n"
            "set -euo pipefail\n"
            "m365 %s\n" % (title, app_version, date_text, " ".join(sh_quote(a) for a in argv)))

# ---- passwords never reach a file (v0.9, as GAMGUI's redact_secrets) ----------
# The session log and the Run-for-each-CSV-row record hold the commands that
# ran; a password typed into Reset password / Create user / Check a password
# must not be stored there. The screen still shows the command as typed.
_SECRET_RE = re.compile(r"(?i)(--(?:new|current)?password(?:\s+|=))(\"[^\"]*\"|'[^']*'|\S+)")

def redact_secrets(text):
    try:
        return _SECRET_RE.sub(lambda m_: m_.group(1) + "********", str(text))
    except Exception:
        return text                       # never let masking break logging

def task_key(category, name):
    # How Favorites / Recent remember a task: "<section>|<task name>".
    return category + "|" + name

def find_task(key):
    # (category, index) of a remembered task, or None if it no longer exists
    # (renamed or removed in a newer version - then it is quietly dropped).
    category, _sep, name = (key or "").partition("|")
    for index, task in enumerate(TASKS.get(category, [])):
        if task["name"] == name:
            return category, index
    return None

def task_matches(category, task, needle):
    # The search box rule (GAMGUI's): every WORD typed must appear somewhere
    # in the section name, the task name or its description, any case.
    if not needle.strip():
        return True
    text = (category + " " + task["name"] + " " + task["desc"]).lower()
    return all(word in text for word in needle.lower().split())


# =============================================================================
# SECTION: Pick... lists for users and groups (v0.6, as GAMGUI)
#   'entra user list' turns any extra --<property> <text> option into a Graph
#   "starts with" filter (CLI v11.11 user-list.js / its docs), so the user
#   list is searched on the server - a tenant can have thousands of users.
#   'entra group list' has no such filter: groups are loaded once and
#   searched here.
# =============================================================================

USER_PICK_KEYS = {"email", "from", "to", "manager", "owner", "leaver"}   # boxes that take a user's UPN

# Pasted look-alike characters (v0.6, from GAMGUI 2.93 - GAM issue #1623): an
# address or ID pasted from Word, Outlook or a web page often carries curly
# quotes or an invisible zero-width space, and Microsoft 365 then answers
# "does not exist" for an account that does exist. Only ADDRESS / ID boxes
# are cleaned; passwords, names and descriptions keep every character. The
# preview shows the cleaned command.
IDENTIFIER_KEYS = {"email", "from", "to", "id", "ids", "skuId", "team", "url", "loc",
                   "manager", "au", "deleted", "owner", "owners", "members", "cc",
                   "leaver"}
NEVER_CLEAN_KEYS = {"password", "display", "first", "last", "desc", "folder", "nick",
                    "title", "dept", "office", "company", "message", "newname", "newteam",
                    "channel", "subject", "body", "service", "plan", "start", "end"}
_ZERO_WIDTH = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")
_WRAP_QUOTES = "\"'\u201c\u201d\u201e\u2018\u2019\u201a\u00ab\u00bb"

def picker_kind(category, task, field):
    # "user", "group" or None - which Pick... list a form box gets. A
    # 'Create ...' / 'Invite ...' task names someone or something NEW (a
    # guest is outside the organization), so it gets no list.
    if field.get("choices") is not None or task["name"].startswith(("Create", "Invite")):
        return None
    if field["key"] in USER_PICK_KEYS:
        return "user"
    if field["key"] == "connection":
        return "connection"
    if field["key"] == "team" or (category == "Groups (Entra)" and field["key"] == "name"):
        return "group"
    return None

def user_search_commands(text):
    # The m365 commands that find users whose display name OR sign-in name
    # starts with what was typed (two Graph filters; results are merged).
    text = (text or "").strip()
    if not text:
        return []
    props = ["--properties", "displayName,userPrincipalName", "--output", "json"]
    return [["entra", "user", "list", "--displayName", text] + props,
            ["entra", "user", "list", "--userPrincipalName", text] + props]

def people_choices(lists):
    # Several 'entra user list' JSON results -> sorted, de-duplicated
    # [(label, upn)] for the list box.
    seen, out = set(), []
    for items in lists:
        for item in items or []:
            upn = (item or {}).get("userPrincipalName")
            if upn and upn.lower() not in seen:
                seen.add(upn.lower())
                out.append(("%s  <%s>" % (item.get("displayName") or upn, upn), upn))
    return sorted(out, key=lambda pair: pair[0].lower())

GROUP_LIST_COMMAND = ["entra", "group", "list", "--properties", "displayName,mail",
                      "--output", "json"]

# ---- Connections (v0.11, like GAMGUI's Section dropdown) ---------------------
# The CLI keeps a connection for every account it was signed in with; the
# window's Connection list is filled from 'connection list' (JSON fields:
# name, connectedAs, authType, active - checked live 10-26-2026).
CONNECTION_LIST_COMMAND = ["connection", "list", "--output", "json"]
GUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

def connection_choices(data):
    # 'connection list' JSON -> [(label, name, active)] in the CLI's order.
    # The label shows the account and the connection's name - a long ID
    # (until renamed with 'connection set') is cut to its first 8 characters
    # there; the full name is what 'connection use --name' takes.
    out = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        name = str(item["name"])
        short = name[:8] if GUID_RE.match(name) else name
        who = item.get("connectedAs") or "(unknown account)"
        out.append(("%s  [%s]" % (who, short), name, bool(item.get("active"))))
    return out

def connection_use_command(name):
    return ["connection", "use", "--name", name]

def changes_connection(argv):
    # True for a command after which "Signed in as" and the Connection list
    # must be checked again (signing in / out, switching, renaming, removing).
    argv = list(argv or [])
    return argv[:1] in (["login"], ["logout"]) or \
        argv[:2] in (["connection", "use"], ["connection", "set"], ["connection", "remove"])

def group_choices(groups, text):
    # All groups -> [(label, display name)] whose name or address CONTAINS
    # every word typed (blank = all).
    words = (text or "").lower().split()
    out = []
    for g in groups or []:
        name = (g or {}).get("displayName") or ""
        label = name + ("  <%s>" % g["mail"] if g.get("mail") else "")
        if name and all(w in label.lower() for w in words):
            out.append((label, name))
    return sorted(out, key=lambda pair: pair[0].lower())
