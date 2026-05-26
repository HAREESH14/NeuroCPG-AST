public class LinkedList {
    static class Node {
        int data;
        Node next;

        Node(int data) {
            this.data = data;
            this.next = null;
        }
    }

    public static Node createNode(int data) {
        Node newNode = new Node(data);
        return newNode;
    }

    public static void insertAtHead(Node[] head, int data) {
        Node newNode = createNode(data);
        newNode.next = head[0];
        head[0] = newNode;
    }

    public static void printList(Node head) {
        Node current = head;
        while (current != null) {
            System.out.print(current.data + " -> ");
            current = current.next;
        }
        System.out.println("NULL");
    }

    public static int search(Node head, int target) {
        Node current = head;
        int index = 0;
        while (current != null) {
            if (current.data == target) {
                return index;
            }
            current = current.next;
            index++;
        }
        return -1;
    }

    public static void main(String[] args) {
        Node[] head = new Node[1];
        insertAtHead(head, 10);
        insertAtHead(head, 20);
        insertAtHead(head, 30);
        printList(head[0]);

        int pos = search(head[0], 20);
        if (pos != -1) {
            System.out.println("Found at index " + pos);
        } else {
            System.out.println("Not found");
        }
    }
}