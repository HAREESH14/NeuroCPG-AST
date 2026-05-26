public class Main {
    public static void main(String[] args) {
        int x = 0;
        // Java does not support goto, so we use a labeled break instead
        // However, since we cannot break from a method, we have to use a loop
        my_label: {
            x = 0;
            // Simulate the goto by skipping the assignment
            break my_label;
            x = 1;
        }
        System.out.println("x is " + x);
    }
}