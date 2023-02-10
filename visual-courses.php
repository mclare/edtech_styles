<?PHP
/* Parse Brock University's Explorance Blue formated CSV file to unique courses durations,
their start and stop dates, and the assocaited default course evaluation dates.

Results are formatted as a Google Chart and displayed in a table.

Uses apc, whih is well supported now, but should work without it.
*/

$start_time = microtime(TRUE);

$apc_cache_length = 60;
// This is a list of courses that are currently offered.
$courses_file = '/var/www/timetables-csv/Courses.csv';

if (isset($_GET['Term'])) $term_tag = filter_var(trim(urldecode($_GET['Term'])),FILTER_SANITIZE_SPECIAL_CHARS);
else $term_tag = '';

$filetime = filemtime($courses_file);
$etag = md5_file($courses_file.$term_tag);

if ($filetime + $apc_cache_length > time()) apc_delete('visual-courses:uniques');

header("Last-Modified: ".gmdate("D, d M Y H:i:s", $filetime)." GMT");

function load_csv_as_array ($file,$refresh = false) {
	$csv_file = array();

		if (($handle = fopen($file, "r")) !== FALSE) {
			stream_set_timeout($file, 4);
			$row = 1;
			$return = array();
		    while (($data = fgetcsv($handle, 0, ",")) !== FALSE) {
				
				//Trim all strings
				$data = array_map('trim', $data);

				array_push($return,$data);	
		        $row++;
		    }
		    fclose($handle);
		}
	
return $return;
}

function gChart_date_object ($t_date, $offest = 0) {
	$t_date = $t_date + $offest;
	$month = date('n',$t_date) - 1;
	return  " new Date(".date('Y',$t_date).", $month, ".date('j',$t_date).") ";
}


/*****************************/

$title = 'Visualization of Course Durations';
?>
<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN"
   "http://www.w3.org/TR/html4/loose.dtd">
<html lang="en">
<!--[if gte IE 5]><![if lt IE 7]>
    <link href="https://lms.brocku.ca/portal/styles/portalstyles-ie5.css" type="text/css" rel="stylesheet" media="all" />
<![endif]><![endif]-->
<link href="/elearn-admin/legacy_one_file.css" type="text/css" rel="stylesheet" media="all" />
<style type="text/css" media="print">
#online_courses {font-size:75%;}
</style>
<head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8">
<?PHP echo "<title>$title</title>"; ?>
<meta name="author" content="Matt Clare" />
<META NAME="ROBOTS" CONTENT="NOINDEX, NOFOLLOW" />

<script type="text/javascript" src="https://code.jquery.com/jquery-3.6.1.slim.min.js"></script>
<script type="text/javascript" src="https://cdn.datatables.net/1.13.1/js/jquery.dataTables.min.js"></script>

<script type="text/javascript" charset="utf-8">
	$(document).ready(function() {
		var oTable = $('#online_courses').dataTable({
		"bPaginate": false
		}
		);
		
		var pTable = $('#active_courses').dataTable({
		"bPaginate": false
		}
		);
	} );
</script>
</head>
<body>	
<?PHP
// Check to see if the HTML caceh file exists and is newer than the CSV file
if (isset($term_tag) && file_exists("../page_cache/$term_tag.html") && filemtime("../page_cache/$term_tag.html") > $filetime) {
	$page = file_get_contents("../page_cache/$term_tag.html");
	$source = "File cache";
}
else {
$source = "Created from CSV source";
$page = '<div id="wrapper">';
	
$page .= "<h1>".$title."</h1>";

$courses = load_csv_as_array($courses_file);

$dates = array();
$uniques = @apc_fetch('visual-courses:uniques'); //Already cached

if (empty($uniques)) {

	$uniques = array();  //2D array of what was found unique in $courses_file (should be cached through apc);
	$uniques['Course_Title'] = array();
	$uniques['TD_Department'] = array();
	$uniques['QBank_Department'] = array();
	$uniques['School'] = array();
	$uniques['Eval_Date_Start'] = array();
	$uniques['Eval_Date_End'] = array();
	$uniques['Course_Date_Start'] = array();
	$uniques['Course_Date_End'] = array();
	$uniques['Report_Date_Release'] = array();
	$uniques['Duration'] = array();
	$uniques['Term'] = array();
	$uniques['Academic_Year'] = array();
	$uniques['Class_Type'] = array();
	$uniques['ContactType'] = array();
	
	$update_uniques = true;
}
else $update_uniques = false;
	
$i = 0;
foreach ($courses as $value) {
	if ($i == 0) {
		$header = $value;
		$h = array_flip($header);
	}
	else if ($i > 0) {
		
		if ($update_uniques) {
			if (!in_array($value[$h['Course_Title']],$uniques['Course_Title'])) array_push($uniques['Course_Title'],$value[$h['Course_Title']]);
			if (!in_array($value[$h['TD_Department']],$uniques['TD_Department'])) array_push($uniques['TD_Department'],$value[$h['TD_Department']]);
			if (!in_array($value[$h['QBank_Department']],$uniques['QBank_Department'])) array_push($uniques['QBank_Department'],$value[$h['QBank_Department']]);
			if (!in_array($value[$h['School']],$uniques['School'])) array_push($uniques['School'],$value[$h['School']]);
		
			if (!in_array($value[$h['Eval_Date_Start']],$uniques['Eval_Date_Start'])) array_push($uniques['Eval_Date_Start'],$value[$h['Eval_Date_Start']]);
			if (!in_array($value[$h['Eval_Date_End']],$uniques['Eval_Date_End'])) array_push($uniques['Eval_Date_End'],$value[$h['Eval_Date_End']]);
			if (!in_array($value[$h['Course_Date_Start']],$uniques['Course_Date_Start'])) array_push($uniques['Course_Date_Start'],$value[$h['Course_Date_Start']]);
			if (!in_array($value[$h['Course_Date_End']],$uniques['Course_Date_End'])) array_push($uniques['Course_Date_End'],$value[$h['Course_Date_End']]);
			if (!in_array($value[$h['Report_Date_Release']],$uniques['Report_Date_Release'])) array_push($uniques['Report_Date_Release'],$value[$h['Report_Date_Release']]);
			if (!in_array($value[$h['Duration']],$uniques['Duration'])) array_push($uniques['Duration'],$value[$h['Duration']]);
			
		
			if (!in_array($value[$h['Term']],$uniques['Term'])) array_push($uniques['Term'],$value[$h['Term']]);
			if (!in_array($value[$h['Academic_Year']],$uniques['Academic_Year'])) array_push($uniques['Academic_Year'],$value[$h['Academic_Year']]);
		
			if (!in_array($value[$h['Class_Type']],$uniques['Class_Type'])) array_push($uniques['Class_Type'],$value[$h['Class_Type']]);
			if (!in_array($value[$h['ContactType']],$uniques['ContactType'])) array_push($uniques['ContactType'],$value[$h['ContactType']]);
		}
		
		if (isset($_GET['Term']) && trim(urldecode($_GET['Term'])) == $value[$h['Term']]) { //working the dates
			//if (isset($_GET['Term']) && trim(urldecode($_GET['Term'])) == $value[$h['Term']] && trim(urldecode($_GET['Academic_Year'])) == $value[$h['Academic_Year']]) { //working the dates
			$duration = intval($value[$h['Duration']]);
			//if ($duration < 10) $duration = "0$duration";
			if (!isset($dates["$duration"])) {
				$dates[$duration]['Eval_Date_Start'] = $value[$h['Eval_Date_Start']];
				$dates[$duration]['Eval_Date_End'] = $value[$h['Eval_Date_End']];
				$dates[$duration]['Course_Date_Start'] = $value[$h['Course_Date_Start']];
				$dates[$duration]['Course_Date_End'] = $value[$h['Course_Date_End']];
				$dates[$duration]['Report_Date_Release'] = $value[$h['Report_Date_Release']];
				$dates[$duration]['Duration'] = $value[$h['Duration']];
				
				$dates[$duration]['unix_Eval_Date_Start'] = strtotime($value[$h['Eval_Date_Start']]);
				$dates[$duration]['unix_Eval_Date_End'] = strtotime($value[$h['Eval_Date_End']]);
				$dates[$duration]['unix_Course_Date_Start'] = strtotime($value[$h['Course_Date_Start']]);
				$dates[$duration]['unix_Course_Date_End'] = strtotime($value[$h['Course_Date_End']]);
				$dates[$duration]['unix_Report_Date_Release'] = strtotime($value[$h['Report_Date_Release']]);
				$dates[$duration]['unix_Duration'] = strtotime($value[$h['Duration']]);
				
				$dates[$duration]['representative_OriginalID'] = $value[$h['OriginalID']];
				$dates[$duration]['QBank_Departments'] =  array($value[$h['QBank_Department']]);
				
			}
			else {
				if (!in_array($value[$h['QBank_Department']], $dates[$duration]['QBank_Departments'] , true)) {
						array_push($dates[$duration]['QBank_Departments'],$value[$h['QBank_Department']]);
				}
			}
		
		}
		//else print "<p>Filters not properly set.</p>";
	}

$i++;	
}

if ($update_uniques) @apc_store('visual-courses:uniques', $uniques, $apc_cache_length); //Store in cache, until TTL out

ksort($dates);

if (isset($_GET['Term'])) {

$page .=  "
<script type=\"text/javascript\" src=\"https://www.gstatic.com/charts/loader.js\"></script>
<script type=\"text/javascript\">
google.charts.load(\"current\", {packages:[\"calendar\",\"timeline\"]});
</script>";

$page .=  '
	<script type="text/javascript">
	 // google.charts.load("current", {packages:["timeline"]});
	  google.charts.setOnLoadCallback(drawChart);
	  function drawChart() {
		  ';

$page .=  "
	    var container2 = document.getElementById('term-timeline');
	    var chart = new google.visualization.Timeline(container2);
	    var dataTable = new google.visualization.DataTable();
	    dataTable.addColumn({ type: 'string', id: 'Event' });
	    dataTable.addColumn({ type: 'string', id: 'Term' });
	    dataTable.addColumn({ type: 'date', id: 'Start' });
	    dataTable.addColumn({ type: 'date', id: 'End' });
		
";

$page .=  "
	    dataTable.addRows([";
foreach ($dates as $value) { 
	//gChart_date_object($value['unix_Eval_Date_End'])
	$page .=   "[ 'Course Start and End', 'Duration $value[Duration] - End ".str_replace('12:00:00 AM','',$value['Course_Date_End'])."', ".gChart_date_object($value['unix_Course_Date_Start']).", ".gChart_date_object($value['unix_Course_Date_End'])."],\n";
	$page .=   "[ 'Eval Start and End', 'Duration $value[Duration] - End ".str_replace('12:00:00 AM','',$value['Eval_Date_End'])."', ".gChart_date_object($value['unix_Eval_Date_Start']).", ".gChart_date_object($value['unix_Eval_Date_End'])."],\n";
		}
		
$page .=  "	    ]);

var options = {
     timeline: { groupByRowLabel: true }
   };

";

$page .=  '
	    chart.draw(dataTable, options);
	  }
	</script>

	<div id="term-timeline" style="width: 100%; height: 800px;"></div>';

$page .=  "

	<script type=\"text/javascript\">
	google.charts.setOnLoadCallback(drawCalChart);

	function drawCalChart() {
	 var dataTable2 = new google.visualization.DataTable();
	    dataTable2.addColumn({ type: 'date', id: 'Date' });
	    dataTable2.addColumn({ type: 'number', id: 'done' });

		dataTable2.addRows([ ";
	
		foreach ($dates as $key => $value) {
			$page .=  "\n [ ".gChart_date_object($value['unix_Eval_Date_End']).", $key],";
		}	
	
$page .=  "
	 	]);

	    var chart = new google.visualization.Calendar(document.getElementById('calendar_basic'));
	
	    var options = {
	      height: 350,
	     title: 'Evaluation End Dates',
	     calendar: { cellSize: 10 },
		 noDataPattern: {
		            backgroundColor: '#E6E6E6',
		            color: '#a0c3ff'
		          },
	   };
	    chart.draw(dataTable2,options);
	}
	</script>

	";
$page .=  '<div id="calendar_basic" style="width: 100%;"></div>';	
$page .=  "<h3>Found Durations in Term $_GET[Term]</h3>";


$page .= '<table id="online_courses" cellspacing="0" class="display" border="1">
	<thead><tr>
		<th>Duration</th><th>Course_Date_Start</th><th>Eval_Date_Start</th><th>Eval_Date_End</th><th>Course_Date_End</th><th>Report_Date_Release</th><th>representative_OriginalID</th><th>QBank_Departments</th>
	</tr></thead>
	<tbody>';
foreach ($dates as $value) { 
	$page .=  "<tr><td>$value[Duration]</td><td>$value[Course_Date_Start]</td><td>$value[Eval_Date_Start]</td><td>$value[Eval_Date_End]</td><td>$value[Course_Date_End]</td><td>$value[Report_Date_Release]</td><td>$value[representative_OriginalID]</td><td><Small>";
		
		
	foreach ($value['QBank_Departments'] as $value2) {
		$page .=  "$value2, ";
	}
	$page .=  "</Small></td></tr>\n";

}

		
$page .= '</tbody>
</table>';

$page .=  "<div style=\"margin:10px\">Count of lines in $courses_file: ".count ($courses).".  File modified ".date("r",$filetime)."</div>"; 

}

$page .= '<hr />
	<div id="control-form">
		<form action="'.$_SERVER['PHP_SELF'].'" method="get" accept-charset="utf-8">
		<!--
			<label>Academic_Year <select name="Academic_Year" id="Academic_Year" onchange="" size="1">';
			
		 foreach ($uniques['Academic_Year'] as $value) $page .=  "<option value=\"".$value."\">$value</option>\n";
$page .= '		</select></label>
		-->	
			<label>Term <select name="Term" id="Term" onchange="" size="1">';
			
		 foreach ($uniques['Term'] as $value) $page .=  "<option value=\"".$value."\">$value</option>\n";

$page .= '	</select></label>
		
			<p><input type="submit" value="Update"></p>
		</form>
	</div>
	<div>
		<strong>Useful and related:</strong> <a href="https://brocku.ca/guides-and-timetables/registration/undergraduate/">Brock University timetable</a> <a href="https://brocku.ca/important-dates/">Brock University Important Dates</a>
	<div>
	</div>';
	
file_put_contents("../page_cache/$term_tag.html",$page);
}

echo $page;

echo "<div><small>Page load took ";
$endtime = microtime(true); 
printf("Page loaded in %f seconds", $endtime - $starttime );
echo ".</small></div>";
	
?>	
</body>
</html>
