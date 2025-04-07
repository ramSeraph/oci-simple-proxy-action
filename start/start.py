import oci
import sys
import base64
import argparse

from pathlib import Path

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Create an Oracle Cloud Infrastructure compute instance.')
    parser.add_argument('--config-file', required=True, help='Location of config file')
    parser.add_argument('--compartment-name', required=True, help='Name of the compartment')
    parser.add_argument('--availability-domain', required=True, help='Name of the availability domain')
    parser.add_argument('--name-suffix', required=True, help='Suffix for all the generated names')
    parser.add_argument('--open-port', required=True, type=int, help='open port')

    parser.add_argument('--shape', required=True, help='Compute shape')
    parser.add_argument('--shape-ocpus', type=int, required=False, default=-1, help='Compute shape number of ocpus')
    parser.add_argument('--shape-memory-in-gbs', type=int, required=False, default=-1, help='Compute shape memory in GB')
    parser.add_argument('--os-name', required=True, help='OS name')
    parser.add_argument('--os-version', required=True, help='OS version')
    parser.add_argument('--ssh-public-key', default='', help='ssh public key location (empty means no key. default: "")')
    parser.add_argument('--cloud-init', required=True, help='Path to cloud-init script file')
    parser.add_argument('--save-ip-address-to', required=True, help='Path to save ip address to')
    
    return parser.parse_args()


# Initialize service clients

def get_compartment_id_by_name(config, identity_client, compartment_name):
    """Get compartment ID by name."""
    # First, get the root compartment (tenancy) ID
    tenancy_id = config.get("tenancy")
    
    # List all compartments in the tenancy
    response = identity_client.list_compartments(
        compartment_id=tenancy_id,
        compartment_id_in_subtree=True
    )
    
    # Find the compartment with the matching name
    for compartment in response.data:
        if compartment.name == compartment_name and compartment.lifecycle_state == "ACTIVE":
            return compartment.id
    
    # If not found
    raise ValueError(f"Compartment with name '{compartment_name}' not found.")

def get_availability_domain(identity_client, compartment_id, ad_name):
    """Get availability domain by name or the first one if name not provided."""
    list_availability_domains_response = identity_client.list_availability_domains(
        compartment_id=compartment_id
    )
    
    for ad in list_availability_domains_response.data:
        if ad.name == ad_name:
            return ad
    raise ValueError(f"Availability domain '{ad_name}' not found.")


def get_image_id(compute, compartment_id, os_name, os_version, shape):
    """Get the image ID for a specific OS and version."""
    list_images_response = compute.list_images(
        compartment_id=compartment_id,
        shape=shape,
        operating_system=os_name,
        operating_system_version=os_version
    )
    
    if not list_images_response.data:
        raise ValueError(f"No images found for {os_name=} {os_version=} {shape=}")
    
    return list_images_response.data[0].id

def create_instance(compute, compartment_id, subnet_id, image_id,
                    availability_domain, shape, shape_config, 
                    display_name, ssh_public_key, cloud_init_file):
    """Create a compute instance."""
    # Read SSH public key from file
    ssh_key = None
    if ssh_public_key != '':
        ssh_key = Path(ssh_public_key).read_text().strip()
    
    instance_details = oci.core.models.LaunchInstanceDetails(
        compartment_id=compartment_id,
        availability_domain=availability_domain,
        shape=shape,
        shape_config=shape_config,
        display_name=display_name,
        source_details=oci.core.models.InstanceSourceViaImageDetails(
            image_id=image_id
        ),
        create_vnic_details=oci.core.models.CreateVnicDetails(
            subnet_id=subnet_id,
            assign_public_ip=True
        )
    )
    cloud_init_base64 = base64.b64encode(Path(cloud_init_file).read_bytes()).decode()

    metadata = { 'user_data': cloud_init_base64 }
    if ssh_key is not None:
        metadata['ssh_authorized_keys'] = ssh_key

    instance_details.metadata = metadata
    
    launch_instance_response = compute.launch_instance(
        launch_instance_details=instance_details
    )
    
    return launch_instance_response.data

def create_vcn(network, compartment_id, vcn_name, cidr_block="10.0.0.0/16"):
    """Create a new Virtual Cloud Network (VCN)."""
    print(f"Creating VCN: {vcn_name}...")
    
    create_vcn_details = oci.core.models.CreateVcnDetails(
        compartment_id=compartment_id,
        display_name=vcn_name,
        cidr_block=cidr_block,
        dns_label=vcn_name.lower().replace('-', '').replace(' ', '')[:15]
    )
    
    vcn = network.create_vcn(create_vcn_details).data
    
    # Wait for VCN to be available
    oci.wait_until(
        network,
        network.get_vcn(vcn.id),
        'lifecycle_state',
        'AVAILABLE',
        max_wait_seconds=300
    )
    
    print(f"VCN created: {vcn.id}")
    return vcn

def create_internet_gateway(network, compartment_id, vcn_id, ig_name):
    """Create an Internet Gateway for the VCN."""
    print(f"Creating Internet Gateway: {ig_name}...")
    
    create_ig_details = oci.core.models.CreateInternetGatewayDetails(
        compartment_id=compartment_id,
        vcn_id=vcn_id,
        display_name=ig_name,
        is_enabled=True
    )
    
    ig = network.create_internet_gateway(create_ig_details).data
    
    # Wait for Internet Gateway to be available
    oci.wait_until(
        network,
        network.get_internet_gateway(ig.id),
        'lifecycle_state',
        'AVAILABLE',
        max_wait_seconds=300
    )
    
    print(f"Internet Gateway created: {ig.id}")
    return ig

def update_default_route_table(network, compartment_id, vcn, ig_id):
    """Update the default route table to use the Internet Gateway."""
    print("Updating default route table...")
    
    # Get the default route table
    route_tables = network.list_route_tables(
        compartment_id=compartment_id,
        vcn_id=vcn.id
    ).data

    for rt in route_tables:
        print(rt.id, rt.display_name)
    
    default_route_table = next(rt for rt in route_tables if rt.display_name == f"Default Route Table for {vcn.display_name}")

    # Create route rule for internet access
    route_rules = [
        oci.core.models.RouteRule(
            destination="0.0.0.0/0",
            destination_type="CIDR_BLOCK",
            network_entity_id=ig_id
        )
    ]
    
    # Update the route table
    update_route_table_details = oci.core.models.UpdateRouteTableDetails(
        route_rules=route_rules
    )
    
    network.update_route_table(default_route_table.id, update_route_table_details)
    print("Default route table updated with Internet Gateway route")
    
    return default_route_table

def create_security_list(network, compartment_id, vcn_id, port, security_list_name):
    """Create a security list with rules for SSH and the specified port."""
    print(f"Creating security list with port {port} open...")
    
    # Ingress rules (incoming traffic)
    ingress_security_rules = [
        # Allow SSH (port 22)
        oci.core.models.IngressSecurityRule(
            protocol="6",  # TCP
            source="0.0.0.0/0",
            source_type="CIDR_BLOCK",
            tcp_options=oci.core.models.TcpOptions(
                destination_port_range=oci.core.models.PortRange(
                    min=22,
                    max=22
                )
            )
        ),
        # Allow specified port
        oci.core.models.IngressSecurityRule(
            protocol="6",  # TCP
            source="0.0.0.0/0",
            source_type="CIDR_BLOCK",
            tcp_options=oci.core.models.TcpOptions(
                destination_port_range=oci.core.models.PortRange(
                    min=port,
                    max=port
                )
            )
        ),
        # Allow ICMP (ping)
        oci.core.models.IngressSecurityRule(
            protocol="1",  # ICMP
            source="0.0.0.0/0",
            source_type="CIDR_BLOCK",
            icmp_options=oci.core.models.IcmpOptions(
                type=3,
                code=4
            )
        )
    ]
    
    # Egress rules (outgoing traffic)
    egress_security_rules = [
        oci.core.models.EgressSecurityRule(
            destination="0.0.0.0/0",
            destination_type="CIDR_BLOCK",
            protocol="all"
        )
    ]
    
    create_security_list_details = oci.core.models.CreateSecurityListDetails(
        compartment_id=compartment_id,
        vcn_id=vcn_id,
        display_name=security_list_name,
        ingress_security_rules=ingress_security_rules,
        egress_security_rules=egress_security_rules
    )
    
    security_list = network.create_security_list(create_security_list_details).data
    
    # Wait for security list to be available
    oci.wait_until(
        network,
        network.get_security_list(security_list.id),
        'lifecycle_state',
        'AVAILABLE',
        max_wait_seconds=300
    )
    
    print(f"Security list created: {security_list.id}")
    return security_list


def create_subnet(network, compartment_id, vcn_id, security_list_id, subnet_name, cidr_block, availability_domain):
    """Create a subnet in the VCN."""
    print(f"Creating subnet: {subnet_name} with CIDR {cidr_block}...")
    
    create_subnet_details = oci.core.models.CreateSubnetDetails(
        compartment_id=compartment_id,
        vcn_id=vcn_id,
        display_name=subnet_name,
        cidr_block=cidr_block,
        dns_label=subnet_name.lower().replace('-', '').replace(' ', '')[:15],
        security_list_ids=[security_list_id],
        availability_domain=availability_domain
    )
    
    subnet = network.create_subnet(create_subnet_details).data
    
    # Wait for subnet to be available
    oci.wait_until(
        network,
        network.get_subnet(subnet.id),
        'lifecycle_state',
        'AVAILABLE',
        max_wait_seconds=300
    )
    
    print(f"Subnet created: {subnet.id}")
    return subnet

def main():
    # Parse command line arguments
    args = parse_arguments()

    config = oci.config.from_file(file_location=args.config_file)
    
    compute_client = oci.core.ComputeClient(config)
    network_client = oci.core.VirtualNetworkClient(config)
    identity_client = oci.identity.IdentityClient(config)

    try:
        # Get compartment ID from compartment name
        compartment_id = get_compartment_id_by_name(config,
                                                    identity_client,
                                                    args.compartment_name)
        print(f"Found compartment ID: {compartment_id}")
        
        # Get availability domain
        availability_domain = get_availability_domain(identity_client,
                                                      compartment_id,
                                                      args.availability_domain)
        print(f"Using availability domain: {availability_domain.name}")

        # Get image ID
        image_id = get_image_id(compute_client,
                                compartment_id, 
                                args.os_name, 
                                args.os_version, 
                                args.shape)
        print(f"Using image ID: {image_id}")

        shape_config = oci.core.models.LaunchInstanceShapeConfigDetails()
        if args.shape_ocpus != -1:
            shape_config.ocpus = args.shape_ocpus

        if args.shape_memory_in_gbs != -1:
            shape_config.memory_in_gbs = args.shape_memory_in_gbs
     
        suffix = args.name_suffix

        vcn = create_vcn(network_client,
                         compartment_id, 
                         f'vcn-{suffix}')

        ig = create_internet_gateway(network_client,
                                     compartment_id, 
                                     vcn.id, 
                                     f'ig-{suffix}')

        update_default_route_table(network_client,
                                   compartment_id, 
                                   vcn, 
                                   ig.id)

        security_list = create_security_list(network_client,
                                             compartment_id, 
                                             vcn.id, 
                                             args.open_port, 
                                             f'sl-{suffix}')

        subnet = create_subnet(network_client,
                               compartment_id, 
                               vcn.id,
                               security_list.id,
                               f'subnet-{suffix}',
                               '10.0.0.0/24',
                               args.availability_domain)
   
        # Create instance
        instance = create_instance(
            compute_client,
            compartment_id=compartment_id,
            subnet_id=subnet.id,
            image_id=image_id,
            availability_domain=args.availability_domain,
            shape=args.shape,
            shape_config=shape_config,
            display_name=f'proxy-{suffix}',
            ssh_public_key=args.ssh_public_key,
            cloud_init_file=args.cloud_init
        )
        
        print("\nInstance being created:")
        print(f"OCID: {instance.id}")
        print(f"Name: {instance.display_name}")
        print(f"State: {instance.lifecycle_state}")
        
        print("\nWaiting for instance to be provisioned...")
        
        # Wait for the instance to become available
        get_instance_response = oci.wait_until(
            compute_client,
            compute_client.get_instance(instance_id=instance.id),
            'lifecycle_state',
            'RUNNING',
            max_wait_seconds=600
        )
        
        print(f"Instance is now {get_instance_response.data.lifecycle_state}")
        
        # Get the public IP address
        vnic_attachments = compute_client.list_vnic_attachments(
            compartment_id=compartment_id,
            instance_id=instance.id
        ).data
        
        vnic = network_client.get_vnic(vnic_attachments[0].vnic_id).data
        Path(args.save_ip_address_to).write_text(str(vnic.public_ip))
        
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
