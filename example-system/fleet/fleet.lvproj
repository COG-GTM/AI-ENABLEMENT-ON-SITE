<?xml version='1.0' encoding='UTF-8'?>
<!-- Synthetic project file for the fleet-discovery demo. Hand-written stand-in for shape only: it points at the
     four public-domain-licensed VIs in ../real-vi/ under "My Computer" and shows how RT and FPGA targets appear
     in a real .lvproj. The RT/FPGA items reference no binaries; nothing here came from a customer. -->
<Project Type="Project" LVVersion="13008000">
	<Item Name="My Computer" Type="My Computer">
		<Item Name="Topic Filter" Type="Folder">
			<Item Name="Create TopicFilter.vi" Type="VI" URL="../real-vi/Create TopicFilter.vi"/>
			<Item Name="Evaluate.vi" Type="VI" URL="../real-vi/Evaluate.vi"/>
		</Item>
		<Item Name="Tests" Type="Folder">
			<Item Name="Test MQTT-4.7.1-2.vi" Type="VI" URL="../real-vi/Test MQTT-4.7.1-2.vi"/>
			<Item Name="Test MQTT-4.7.1-3.vi" Type="VI" URL="../real-vi/Test MQTT-4.7.1-3.vi"/>
		</Item>
		<Item Name="Dependencies" Type="Dependencies"/>
		<Item Name="Build Specifications" Type="Build"/>
	</Item>
	<Item Name="RT Controller" Type="RT CompactRIO">
		<Item Name="RT Main.vi" Type="VI" URL="rt/RT Main.vi"/>
		<Item Name="Chassis" Type="cRIO Chassis">
			<Item Name="FPGA Target" Type="FPGA Target">
				<Item Name="FPGA Main.vi" Type="VI" URL="fpga/FPGA Main.vi"/>
			</Item>
		</Item>
		<Item Name="Dependencies" Type="Dependencies"/>
		<Item Name="Build Specifications" Type="Build"/>
	</Item>
</Project>
