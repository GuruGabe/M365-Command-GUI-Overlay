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
  T("List Microsoft 365 groups (with site address)",
    "Every Microsoft 365 group (every Team has one), with its SharePoint site address.",
    "entra m365group list --withSiteUrl --output text", []),
  T("Microsoft 365 groups without owners",
    "Groups nobody owns - nobody can manage their members or settings.",
    "entra m365group list --orphaned --output text", []),
  T("Get a Team / Microsoft 365 group's info",
    "Shows one Microsoft 365 group (or Team), with its site address.",
    "entra m365group get --displayName {team} --withSiteUrl --output text",
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
  T("Search the audit log",
    "Audit records of one kind (sign-ins and directory changes, Exchange, SharePoint...). "
    "Dates like 2026-10-01. Needs audit logging switched on.",
    "purview auditlog list --contentType {ctype} [--startTime {start}] [--endTime {end}] --output text",
    [F("Kind of records", "ctype", choices=["AzureActiveDirectory", "Exchange", "SharePoint", "General", "DLP"]),
     F("From (optional) e.g. 2026-10-01", "start", False), F("Until (optional)", "end", False)]),
  T("Retention labels", "The retention labels defined in Purview.",
    "purview retentionlabel list --output text", []),
  T("Sensitivity labels", "The sensitivity labels defined in Purview.",
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
  T("Active users by product (counts)", "How many people used each Microsoft 365 service per day.",
    "tenant report activeusercounts --period {period} --output text",
    [F("Period", "period", choices=["D7", "D30", "D90", "D180"], default="D30")]),
  T("Active users - per person", "Each person's last activity date in each service.",
    "tenant report activeuserdetail --period {period} --output text",
    [F("Period", "period", choices=["D7", "D30", "D90", "D180"], default="D30")]),
  T("Teams activity - per person", "Chats, meetings and calls per person.",
    "teams report useractivityuserdetail --period {period} --output text",
    [F("Period", "period", choices=["D7", "D30", "D90", "D180"], default="D30")]),
  T("Teams devices used - per person", "Which devices (Windows, Mac, iOS, Android, web) people use Teams on.",
    "teams report deviceusageuserdetail --period {period} --output text",
    [F("Period", "period", choices=["D7", "D30", "D90", "D180"], default="D30")]),
  T("OneDrive storage - per account", "Files and storage used in each OneDrive.",
    "onedrive report usageaccountdetail --period {period} --output text",
    [F("Period", "period", choices=["D7", "D30", "D90", "D180"], default="D30")]),
  T("OneDrive activity - per person", "Files viewed, edited, synced and shared per person.",
    "onedrive report activityuserdetail --period {period} --output text",
    [F("Period", "period", choices=["D7", "D30", "D90", "D180"], default="D30")]),
  T("Mailbox storage - per mailbox", "Size and item counts of every mailbox.",
    "outlook report mailboxusagedetail --period {period} --output text",
    [F("Period", "period", choices=["D7", "D30", "D90", "D180"], default="D30")]),
  T("Email activity - per person", "Mail sent, received and read per person.",
    "outlook report mailactivityuserdetail --period {period} --output text",
    [F("Period", "period", choices=["D7", "D30", "D90", "D180"], default="D30")]),
  T("SharePoint site usage - per site", "Files, storage and activity of each SharePoint site.",
    "spo report siteusagedetail --period {period} --output text",
    [F("Period", "period", choices=["D7", "D30", "D90", "D180"], default="D30")]),
 ],
 "Roles and admin units": [
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
 ],
 "Security": [
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
    return not task.get("workflow") and "--output text" in task.get("template", "")

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

USER_PICK_KEYS = {"email", "from", "to", "manager", "owner"}   # boxes that take a user's UPN

# Pasted look-alike characters (v0.6, from GAMGUI 2.93 - GAM issue #1623): an
# address or ID pasted from Word, Outlook or a web page often carries curly
# quotes or an invisible zero-width space, and Microsoft 365 then answers
# "does not exist" for an account that does exist. Only ADDRESS / ID boxes
# are cleaned; passwords, names and descriptions keep every character. The
# preview shows the cleaned command.
IDENTIFIER_KEYS = {"email", "from", "to", "id", "ids", "skuId", "team", "url", "loc",
                   "manager", "au", "deleted", "owner", "owners", "members", "cc"}
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
