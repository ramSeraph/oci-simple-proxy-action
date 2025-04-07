import argparse

import oci

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Create an Oracle Cloud Infrastructure compute instance.')
    parser.add_argument('--config-file', required=True, help='Location of config file')
    parser.add_argument('--compartment-name', required=True, help='Name of the compartment')
    parser.add_argument('--name-suffix', required=True, help='Suffix for all the generated names')

    return parser.parse_args()
 
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

def get_instance_by_name(compute, compartment_id, instance_name):
    """Get instance by name."""
    instances = compute.list_instances(
        compartment_id=compartment_id
    ).data
    
    for instance in instances:
        if instance.display_name == instance_name and instance.lifecycle_state != "TERMINATED":
            return instance
    
    raise ValueError(f"Instance with name '{instance_name}' not found.")


def terminate_instance(compute, instance_id, wait=True):
    """Terminate a compute instance."""
    print(f"Terminating instance: {instance_id}...")
    compute.terminate_instance(instance_id)
    
    if wait:
        try:
            oci.wait_until(
                compute,
                compute.get_instance(instance_id),
                'lifecycle_state',
                'TERMINATED',
                max_wait_seconds=300
            )
            print(f"Instance {instance_id} terminated successfully.")
        except oci.exceptions.ServiceError as e:
            if e.status == 404:
                print(f"Instance {instance_id} terminated successfully.")
            else:
                raise

def delete_vcn(network, vcn_id, wait=True):
    """Delete a VCN."""
    print(f"Deleting VCN: {vcn_id}...")
    network.delete_vcn(vcn_id)
    
    if wait:
        try:
            oci.wait_until(
                network,
                network.get_vcn(vcn_id),
                'lifecycle_state',
                'TERMINATED',
                max_wait_seconds=300
            )
            print(f"VCN {vcn_id} deleted successfully.")
        except oci.exceptions.ServiceError as e:
            if e.status == 404:
                print(f"VCN {vcn_id} deleted successfully.")
            else:
                raise


def get_vcn_by_name(network, compartment_id, vcn_name):
    """Get VCN by name."""
    vcns = network.list_vcns(
        compartment_id=compartment_id
    ).data
    
    for vcn in vcns:
        if vcn.display_name == vcn_name and vcn.lifecycle_state != "TERMINATED":
            return vcn
    
    raise ValueError(f"VCN with name '{vcn_name}' not found.")

def delete_internet_gateway(network, ig_id, wait=True):
    """Delete an internet gateway."""
    print(f"Deleting internet gateway: {ig_id}...")
    network.delete_internet_gateway(ig_id)
    
    if wait:
        try:
            oci.wait_until(
                network,
                network.get_internet_gateway(ig_id),
                'lifecycle_state',
                'TERMINATED',
                max_wait_seconds=300
            )
            print(f"Internet gateway {ig_id} deleted successfully.")
        except oci.exceptions.ServiceError as e:
            if e.status == 404:
                print(f"Internet gateway {ig_id} deleted successfully.")
            else:
                raise

def get_internet_gateways(network, compartment_id, vcn_id):
    """Get all internet gateways for a VCN."""
    return network.list_internet_gateways(
        compartment_id=compartment_id,
        vcn_id=vcn_id
    ).data


def update_route_table(network, route_table_id):
    """Reset route table to have no rules."""
    print(f"Resetting route table: {route_table_id}...")
    update_route_table_details = oci.core.models.UpdateRouteTableDetails(
        route_rules=[]
    )
    
    network.update_route_table(route_table_id, update_route_table_details)
    print(f"Route table {route_table_id} updated successfully.")

def delete_security_list(network, security_list_id, wait=True):
    """Delete a security list."""
    print(f"Deleting security list: {security_list_id}...")
    network.delete_security_list(security_list_id)
    
    if wait:
        try:
            oci.wait_until(
                network,
                network.get_security_list(security_list_id),
                'lifecycle_state',
                'TERMINATED',
                max_wait_seconds=300
            )
            print(f"Security list {security_list_id} deleted successfully.")
        except oci.exceptions.ServiceError as e:
            if e.status == 404:
                print(f"Security list {security_list_id} deleted successfully.")
            else:
                raise

def get_route_tables(network, compartment_id, vcn_id):
    """Get all route tables for a VCN."""
    return network.list_route_tables(
        compartment_id=compartment_id,
        vcn_id=vcn_id
    ).data

def get_security_lists(network, compartment_id, vcn_id):
    """Get all security lists for a VCN."""
    return network.list_security_lists(
        compartment_id=compartment_id,
        vcn_id=vcn_id
    ).data

def get_subnet_by_name(network, compartment_id, vcn_id, subnet_name):
    """Get subnet by name."""
    subnets = network.list_subnets(
        compartment_id=compartment_id,
        vcn_id=vcn_id
    ).data
    
    for subnet in subnets:
        if subnet.display_name == subnet_name and subnet.lifecycle_state != "TERMINATED":
            return subnet
    
    raise ValueError(f"Subnet with name '{subnet_name}' not found.")

def delete_subnet(network, subnet_id, wait=True):
    """Delete a subnet."""
    print(f"Deleting subnet: {subnet_id}...")
    network.delete_subnet(subnet_id)
    
    if wait:
        try:
            oci.wait_until(
                network,
                network.get_subnet(subnet_id),
                'lifecycle_state',
                'TERMINATED',
                max_wait_seconds=300
            )
            print(f"Subnet {subnet_id} deleted successfully.")
        except oci.exceptions.ServiceError as e:
            if e.status == 404:
                print(f"Subnet {subnet_id} deleted successfully.")
            else:
                raise

def main():
    # Parse command line arguments
    args = parse_arguments()

    config = oci.config.from_file(file_location=args.config_file)
    
    compute_client = oci.core.ComputeClient(config)
    network_client = oci.core.VirtualNetworkClient(config)
    identity_client = oci.identity.IdentityClient(config)

    suffix = args.name_suffix

    compartment_id = get_compartment_id_by_name(config,
                                                identity_client,
                                                args.compartment_name)

    try:
        instance = get_instance_by_name(compute_client, compartment_id, f'proxy-{suffix}')
        terminate_instance(compute_client, instance.id)
    except Exception as ex:
        print(f'ERROR: deleting instance proxy-{suffix} failed with ex: {ex}.. continuing')

    vcn = get_vcn_by_name(network_client, compartment_id, f'vcn-{suffix}')

    subnet = get_subnet_by_name(network_client, compartment_id, vcn.id, f'subnet-{suffix}')
    print(f"Found subnet: {subnet.id} ({subnet.display_name})")

    # deleting subnet
    delete_subnet(network_client, subnet.id)

    # clear routing tables
    route_tables = get_route_tables(network_client, compartment_id, vcn.id)
    for rt in route_tables:
        if len(rt.route_rules) > 0:
            update_route_table(network_client, rt.id)

    # delete security lists
    security_lists = get_security_lists(network_client, compartment_id, vcn.id)
    for sl in security_lists:
        if sl.display_name != f"Default Security List for {vcn.display_name}":
            delete_security_list(network_client, sl.id)

    # delete internet_gateways
    internet_gateways = get_internet_gateways(network_client, compartment_id, vcn.id)
    for ig in internet_gateways:
        delete_internet_gateway(network_client, ig.id)

    # delete vcn
    delete_vcn(network_client, vcn.id)


if __name__ == "__main__":
    main()
