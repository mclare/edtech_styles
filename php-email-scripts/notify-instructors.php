<?php
//Reminder, turn on JIRA's option to ignore automatic responses before sending!!!
//This script will send an email to all users in the Instructor role in a Sakai Project Site
//Credit goes to GitHub CoPilot ;)
//Source CSV files
$sakaiSitesFile = 'non-course-site-enrollment-20230228-092402.csv'; //Non-Course Site Enrollment report exported from https://data.ca.longsight.com/textreport
$BLEUsersFile = 'Users.csv'; //From Brightspace Data Hub
$DoNotBotherUsersFile = 'DoNotBotherUsers.csv';
$SoftDeletedSitesFile = 'softDeletedSites.csv'; //This is the worst data we have. This is not included in data.ca.longsight.com reports, it is copyied from Admin Site Setup.
// We can append "Do not bother sites" to the soft Delted list, this includes sites that are already migrated to Brightspace, listed in https://brocku.sharepoint.com/:x:/r/sites/NextLMSExploration/Shared%20Documents/General/Implementation/Project%20Sites/Brightspace%20Project%20Site%20Tracking.xlsx?d=wa425044f0d6c461cb442afe59aedede1&csf=1&web=1&e=qmCMlN

//Strings used below
$sakai="lms.brocku.ca";
$brightspace="brightspace.brocku.ca";
$from = "edtech@brocku.ca";
$subject = "Reminder about Sakai Project Sites";
$message = array("<p>This is a reminder that on June 30, 2023 <a href=\"https://$sakai/\">lms.brocku.ca</a> will no longer point to Sakai. Navigation links across Brock University’s web presence will begin to point to <a href=\"https://$brightspace/\">Brightspace</a>.</p>
<p>You can learn more about <a href=\"https://brocku.ca/pedagogical-innovation/next-lms/\">Brock University's LMS transition from Sakai to Brightspace on the Centre for Pedagogical Innovation (CPI) website</a>.</p>
<p>New project sites can be created using the Create Project Site widget on the main page of <a href=\"https://$brightspace/\">Brightspace</a> right now.</p>
<p>As someone in the Instructor role in the following Sakai %s, you may wish to take action on the following %u Sakai Project Sites before June 30, 2023:</p>"); //Note the %u for the sprintf later
$message[]="<p>Your options include:</p>
<ul>
<li>Allowing the site to be archived according to <a href=\"https://brocku.sharepoint.com/sites/Records-Management/SitePages/Course-Materials.aspx\">Brock University's LMS data retention schedule</a></li>
<li>Export the site content (<a href=\"https://docu.brocku.ca/sakai/index.php/Create_a_zip_archive_file_in_Resources\">Compress Resources into a ZIP file</a>, <a href=\"https://docu.brocku.ca/sakai/index.php/Export_grades_from_Gradebook\">export Gradebook data</a>, etc.)</li>
<li>Contact the CPI about migrating the site to Brightspace</li>
<li>Delete the site in the Site Setup area of your Home in <a href=\"https://$sakai/\">Sakai</a></li>
</ul>
<p>The CPI is offering Brightspace training on an ongoing basis, you can sign up for training on <a href=\"https://experiencebu.brocku.ca/organization/cpi\">ExperienceBU</a>.</p>
<p>Academic courses in Sakai from 2018FW to 2022SP/SU have been migrated into Brightspace (see courses with the prefix \"Sakai:\"). This process will be repeated for 2022-23FW content as well.</p>
<p>Please reach out to <a href=\"mailto:edtech@brocku.ca\">edtech@brocku.ca</a> if you have any questions about this process.</p>
";
$messageHTML=array("<html><head><title>$subject</title></head><body><div id=\"email-wrap\" style='background: #FFF;color: #151515;font-size: 1.1em;font-family: \"Bliss Light\",\"Trebuchet MS\",sans-serif;font-weight: 200;'>","</div></body></html>");


$send = "DEV"; //Set to "TESTING" to send to yourself, or "SEND" to send to the users
// print statements will be sent to stdout, so you can redirect them to a file
// execute with php notify-instructors.php or php notify-instructors.php > test-run.html


/************ Processing *****************/

$userSites =  array();
$siteIDtoTitle = array();
$toSend = array(); //Will be an array of arrays of users the E-Mail to send
$siteInstructorCounts =  array();
$activeUsers = array();
$doNotBotherUsers = array();
$softDeletedSites = array();
$logs = array();

$file = fopen($sakaiSitesFile, 'r');
$header = fgetcsv($file);
$role = array_search("role", $header);
$username = array_search("username", $header);
$siteid = array_search("siteid", $header);
$title = array_search("title", $header);

//Read the file and create an array of users and their sites
while (($data = fgetcsv($file)) !== FALSE) {
    if ($data[$role] == "Instructor") {
        // Do something with the data
        $userLocal = trim($data[$username]);
        $siteidLocal = trim($data[$siteid]);
        $siteTitleLocal = trim($data[$title]);

        if (!isset($userSites[$userLocal])) $userSites[$userLocal] = array($siteidLocal); //If we haven't seen this user before, create an array for them
        else array_push($userSites[$userLocal],$siteidLocal);
        if (!isset($siteIDtoTitle[$siteidLocal])) $siteIDtoTitle[$siteidLocal] = $siteTitleLocal;//If we haven't seen this site before, create an mapping of its title
        if (!isset($siteInstructorCounts[$siteidLocal])) $siteInstructorCounts[$siteidLocal] = 1;//If we haven't seen this site before, add an instructor record
        else $siteInstructorCounts[$siteidLocal]++; //If we have seen this site before, increment the instructor count
    }
}
fclose($file);

//Read the file of user we shouldn't E-Mail
$file = fopen($DoNotBotherUsersFile, 'r');
$header = fgetcsv($file);
$BLEUserName = array_search("UserName", $header);
while (($data = fgetcsv($file)) !== FALSE) {
    $doNotBotherUsers[]= $data[$BLEUserName];
}
fclose($file);

//Read the file of sites that are currently soft deleted
$file = fopen($SoftDeletedSitesFile, 'r');
$header = fgetcsv($file);
$SakaiAdminWorksiteTitle = array_search("Worksite Title", $header);

while (($data = fgetcsv($file)) !== FALSE) {
    $softDeletedSites[]= trim($data[$SakaiAdminWorksiteTitle]);
}
fclose($file);

//Create array of active users based on Brightspace records
//Read the file and create an array of users and their Names
$file = fopen($BLEUsersFile, 'r');
$header = fgetcsv($file);
$OrgRoleId = array_search("OrgRoleId", $header); //122 Instructor, 124 Local Admin
$BLEUserName = array_search("UserName", $header);
$BLEFirstName = array_search("FirstName", $header);
$BLELastName = array_search("LastName", $header);
$BLELastAccessed = array_search("LastAccessed", $header);
$BLEExternalEmail = array_search("ExternalEmail", $header);

while (($data = fgetcsv($file)) !== FALSE) {
    if ($data[$OrgRoleId] == 122 || $data[$OrgRoleId] == 124) {
        $activeUsers[$data[$BLEUserName]] = array("FirstName"=>$data[$BLEFirstName],"LastName"=>$data[$BLELastName],"LastAccessed"=>$data[$BLELastAccessed],"BLEExternalEmail"=>$data[$BLEExternalEmail]);
    }
}
fclose($file);

//Create the message for each user
foreach ($userSites as $user => $sites) {
    $sitesNotified = 0;
    if (isset($activeUsers[$user]) && !in_array($user,$doNotBotherUsers)){
    $toSend[$user] = array('email' => "$user@brocku.ca");
    $toSend[$user]['message'] = "\n<!--Last BLE Access ".$activeUsers[$user]['LastAccessed']." -->\n <p>Dear ".$activeUsers[$user]['FirstName'].",</p>";
    $list=""; //variable to hold the list of sites bufferd to be added to the message
    foreach ($sites as $site) {
        if (in_array($siteIDtoTitle[$site],$softDeletedSites)) $logs[] = "Excluding Soft Deleted Site $site:".$siteIDtoTitle[$site]." found for user $user";
        else {
            $sitesNotified++;
            if (isset($siteInstructorCounts[$site]) && $siteInstructorCounts[$site]> 1) $list .= "<li><a href=\"https://$sakai/portal/site/$site\">".$siteIDtoTitle[$site]."</a> <small>(".$siteInstructorCounts[$site]." total instructors)</small></li>\n";
            else $list .= "<li><a href=\"https://$sakai/portal/site/$site\">".$siteIDtoTitle[$site]."</a></li>\n";
        }
    }
    if ($sitesNotified == 1) $sites = "site";
    else $sites = "sites";
    $toSend[$user]['message'] .= sprintf($message[0],$sites,$sitesNotified);
    $toSend[$user]['message'] .= '<ol>'.$list.'</ol>'.$message[1];}
    elseif (in_array($user,$doNotBotherUsers)) $logs[] = "User $user in our Do Not Bother list";
    else $logs[] = "User $user not found in Brightspace";
    if ($sitesNotified == 0) unset($toSend[$user]); //If we didn't find any sites to notify the user about, remove them from the list. Affected by soft deleted sites.
}

/* todo:
Load last modfied date for each site?
*/

$sent = 0;
//Get ready to send message to each user
//Print statements for monitoring, stdout, etc.
print $messageHTML[0];

foreach ($toSend as $user => $data) {

    $to = $data['email'];
    $headers = "From: $from\r\n";
    $headers .= "MIME-Version: 1.0\r\n";
    $headers .= "Content-Type: text/html; charset=ISO-8859-1\r\n";
    $headers .= 'X-Mailer: PHP/' . phpversion();

    $emailMessage = "<!DOCTYPE html>
    <html><head></head><body style=\"color: rgb(32, 33, 34); font-family: Verdana; font-size: 12pt;\">".$data['message']."</body></html>";

    print "<hr />\n<pre>sent: $sent <hr /><div>";
    print "\nto: ".$to;
    print "\nsubject: ".$subject."</pre>";
    print "\n<!--message--><div style=\"color: rgb(32, 33, 34); font-family: Verdana; font-size: 12pt;\">".strip_tags($emailMessage,array('a','li','ol','ul','small','p','br','hr'));
    print "</div></div>\n";

    //Set to "TESTING" to send to yourself, or "SEND" to send to the users
   if ($send == "SEND") mail($to, $subject, $emailMessage, $headers);
   elseif ($send == "TESTING" && $sent < 10) mail('mclare@brocku.ca', $subject, $emailMessage, $headers);
   $sent++;
}
$logs[] = "Sent $sent messages";

print "<h1>Logs</h1><pre>";
foreach ($logs as $value) {
    print "$value\n";
}
print "</pre>";
print $messageHTML[1];
?>
